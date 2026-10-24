"""E2E 支撑回归：验证模型门控、控制授权、终端输出，以及服务失败后的资源清理。"""

import asyncio
from contextlib import asynccontextmanager
import os
from types import SimpleNamespace
import sys

import httpx
from langchain_core.messages import HumanMessage
import pytest

from tests.support import e2e


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["hold", "fail"])
async def test_model_waits_for_explicit_release_and_closes(kind):
    """增量先于终止结果交付；释放后完成或失败，两个分支都登记清理。"""
    model = e2e.ControlledModel()
    prompt = model.prepare(kind)
    stream = model._astream([HumanMessage(content=prompt)])
    first = await anext(stream)
    assert first.message.content == "已收到部分回答"
    pending = asyncio.create_task(anext(stream))
    await model.scenario(prompt).waiting.wait()
    assert not pending.done()
    model.scenario(prompt).released.set()
    if kind == "fail":
        with pytest.raises(RuntimeError, match="模拟生成失败"):
            await pending
    else:
        assert (await pending).message.content == "，现在完成。"
    await stream.aclose()
    assert model.scenario(prompt).closed


@pytest.mark.anyio
async def test_cancelled_model_releases_generator():
    """图取消等待中的模型时，清理状态无需先释放门控就能更新。"""
    model = e2e.ControlledModel()
    prompt = model.prepare("hold")
    stream = model._astream([HumanMessage(content=prompt)])
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await model.scenario(prompt).waiting.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert model.scenario(prompt).closed


@pytest.mark.anyio
async def test_control_routes_require_run_token_and_scope_scenarios():
    """只有持有本次令牌的 fixture 能创建和释放场景，控制不需要业务数据库。"""
    model = e2e.ControlledModel()
    app = e2e.build_test_app(None, model, "test-token")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/__e2e__/scenarios", json={"kind": "hold"})).status_code == 403
        headers = {"Authorization": "Bearer test-token"}
        created = await client.post("/__e2e__/scenarios", json={"kind": "hold"}, headers=headers)
        prompt = created.json()["prompt"]
        assert (await client.get(f"/__e2e__/scenarios/{prompt}", headers=headers)).json() == {"started": False, "closed": False}
        assert (await client.post(f"/__e2e__/scenarios/{prompt}/release", headers=headers)).status_code == 200
        assert model.scenario(prompt).released.is_set()
        assert (await client.get("/__e2e__/scenarios/unknown", headers=headers)).status_code == 404


class ServerStub:
    """可直接观察退出的服务替身，不绑定真实端口或运行 HTTP。"""

    def __init__(self, fail=False):
        """记录是否在启动阶段失败，并建立用于等待退出的事件。"""
        self.started = False
        self.fail = fail
        self.stop = asyncio.Event()
        self.finished = False

    @property
    def should_exit(self):
        """返回服务是否已经收到退出请求。"""
        return self.stop.is_set()

    @should_exit.setter
    def should_exit(self, value):
        """把正式服务器的退出属性转换为可等待事件。"""
        if value:
            self.stop.set()

    async def serve(self, **kwargs):
        """模拟启动失败或正常等待退出，最终登记任务完成。"""
        try:
            if self.fail:
                raise RuntimeError("startup failed")
            self.started = True
            await self.stop.wait()
        finally:
            self.finished = True


@pytest.mark.anyio
async def test_server_closes_listener_and_models_after_test_failure():
    """浏览器阶段异常不妨碍释放等待模型、退出服务和关闭监听套接字。"""
    server = ServerStub()
    listener = e2e.reserve_listener()
    model = e2e.ControlledModel()
    prompt = model.prepare("hold")
    with pytest.raises(RuntimeError, match="browser failed"):
        async with e2e.running_server(server, listener, model):
            raise RuntimeError("browser failed")
    assert server.finished and listener.fileno() == -1
    assert model.scenario(prompt).released.is_set()


@pytest.mark.anyio
async def test_startup_failure_still_closes_listener():
    """服务在就绪前失败时保留错误，监听与任务仍完成回收。"""
    listener = e2e.reserve_listener()
    with pytest.raises(RuntimeError, match="startup failed"):
        async with e2e.running_server(ServerStub(fail=True), listener, e2e.ControlledModel()):
            pytest.fail("启动失败后不应进入浏览器阶段")
    assert listener.fileno() == -1


@pytest.mark.anyio
async def test_build_failure_does_not_create_database(monkeypatch):
    """前端构建失败时立即返回退出码，不初始化数据库资源。"""
    async def rejected_build(*args):
        """模拟构建工具返回非零状态，不运行真实子进程。"""
        return 7

    def forbidden_database():
        """防止失败构建继续读取配置或创建临时库。"""
        pytest.fail("构建失败后不应准备数据库")

    monkeypatch.setattr(e2e, "run_command", rejected_build)
    monkeypatch.setattr(e2e, "load_database_settings", forbidden_database)
    assert await e2e.run_e2e([]) == 7


@pytest.mark.anyio
async def test_browser_failure_exits_database_context(monkeypatch):
    """浏览器非零退出仍按服务、数据库的逆依赖顺序清理，并恢复入口替换。"""
    events = []
    commands = iter([0, 9])

    async def command(*args):
        """分别模拟成功构建与失败浏览器执行。"""
        return next(commands)

    @asynccontextmanager
    async def database(base, **kwargs):
        """记录临时库上下文是否在服务退出后清理。"""
        events.append("database-open")
        try:
            yield SimpleNamespace(postgres_db="zhizhou_test_unit")
        finally:
            events.append("database-close")

    @asynccontextmanager
    async def server(*args):
        """替代服务任务并回收启动器传来的套接字。"""
        events.append("server-open")
        try:
            yield "http://127.0.0.1:12345"
        finally:
            args[1].close()
            events.append("server-close")

    monkeypatch.setattr(e2e, "run_command", command)
    monkeypatch.setattr(e2e, "temporary_database", database)
    monkeypatch.setattr(e2e, "running_server", server)
    async def configured(settings):
        """记录正式模型配置准备发生在服务启动前，隔离本例数据库。"""
        events.append("model-configured")
    monkeypatch.setattr(e2e, "configure_test_model", configured)
    monkeypatch.setattr(e2e, "load_database_settings", lambda: None)
    assert await e2e.run_e2e([]) == 9
    assert events == ["database-open", "model-configured", "server-open", "server-close", "database-close"]


@pytest.mark.anyio
async def test_command_preserves_nonzero_exit_without_database():
    """独立解释器的失败退出码原样返回，不被启动器误报成功。"""
    assert await e2e.run_command([sys.executable, "-c", "raise SystemExit(7)"], {}) == 7


@pytest.mark.anyio
@pytest.mark.parametrize("returncode", [0, 7])
@pytest.mark.parametrize("capture_kind", ["capfd", "capsys"])
async def test_command_displays_output_and_errors_before_return(request, capture_kind, returncode):
    """成功和失败的 CLI 均显示双输出流，父级输出无需提供可继承的文件句柄。"""
    capture = request.getfixturevalue(capture_kind)
    # 独立解释器模拟构建或测试报告；UTF-8 与启动器的实际子进程环境一致。
    script = (
        "import sys; "
        "print('测试汇总：18 passed', flush=True); "
        "print('测试诊断：失败详情', file=sys.stderr, flush=True); "
        f"raise SystemExit({returncode})"
    )
    result = await e2e.run_command(
        [sys.executable, "-c", script], {**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    captured = capture.readouterr()
    assert result == returncode
    assert "测试汇总：18 passed" in captured.out
    assert "测试诊断：失败详情" in captured.err


@pytest.mark.anyio
async def test_command_drains_both_pipes_without_waiting_for_exit(capsys):
    """双输出流超过管道容量时仍持续读取，避免等待子进程退出产生死锁。"""
    # 两路大输出都必须被消费；若等退出后才读，或依次读到 EOF，子进程会阻塞。
    script = (
        "import sys; "
        "sys.stdout.write('A' * 262144); sys.stdout.flush(); "
        "sys.stderr.write('B' * 262144); sys.stderr.flush()"
    )
    async with asyncio.timeout(10):
        assert await e2e.run_command([sys.executable, "-c", script], dict(os.environ)) == 0
    captured = capsys.readouterr()
    assert captured.out == "A" * 262144
    assert captured.err == "B" * 262144


@pytest.mark.anyio
async def test_cancelled_command_stops_process_and_finishes_output(monkeypatch, capsys):
    """运行中的输出及时可见，取消时结束子进程并读完诊断，避免后台线程跨用例存活。"""
    processes = []
    start = e2e.subprocess.Popen

    def record_process(*args, **kwargs):
        """保留真实进程句柄，供取消后验证清理确实完成。"""
        process = start(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(e2e.subprocess, "Popen", record_process)
    # 输出就绪信号后等待取消，不以固定时长碰运气判断子进程是否已经启动。
    script = (
        "import sys, threading; "
        "print('READY_ERR', file=sys.stderr, flush=True); "
        "print('READY_OUT', flush=True); threading.Event().wait()"
    )
    task = asyncio.create_task(e2e.run_command([sys.executable, "-c", script], dict(os.environ)))
    output = ""
    errors = ""
    try:
        async with asyncio.timeout(10):
            while "READY_OUT" not in output:
                captured = capsys.readouterr()
                output += captured.out
                errors += captured.err
                # 条件轮询只等待子进程的明确就绪信号。
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        captured = capsys.readouterr()
        assert "READY_ERR" in errors + captured.err
        assert processes[0].poll() is not None
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
