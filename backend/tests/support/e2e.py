"""前端 E2E 本地启动器：真实业务服务连接临时库，仅替换第三方模型。

从 frontend 执行 pnpm test:e2e。生产构建和 Playwright 使用项目内 CLI，
数据库复用已有测试支撑；模型控制路由仅装配在本模块创建的测试应用中。
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
from typing import TextIO
from unittest.mock import patch
from functools import partial
from uuid import uuid4

from fastapi import HTTPException, Request
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic import PrivateAttr
import uvicorn

from app.core.event_loop import create_event_loop
from app.core.settings import load_database_settings
from tests.support.apps import make_app
from tests.support.fakes.chat import StubChatModel
from tests.support.postgres import temporary_database
from tests.support.postgres import seed_model_configuration
from app.db.business import open_business_database
from app.services.model_config import ModelConfigService
from app.llm.runtime import ConfiguredChatAgent

FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "frontend"


@dataclass
class ModelScenario:
    """一例模型调用的独立门控状态；只在测试后端的同一事件循环中访问。"""

    kind: str
    released: asyncio.Event = field(default_factory=asyncio.Event)
    waiting: asyncio.Event = field(default_factory=asyncio.Event)
    started: bool = False
    closed: bool = False


class ControlledModel(StubChatModel):
    """保留真实图和工具调用，只用本地可控模型替代付费供应商。"""

    _scenarios: dict[str, ModelScenario] = PrivateAttr(default_factory=dict)

    def prepare(self, kind: str) -> str:
        """创建独立的等待或失败场景，返回浏览器可发送的唯一提示文本。"""
        if kind not in {"hold", "fail"}:
            raise ValueError("未知模型测试场景")
        prompt = f"受控测试_{uuid4().hex}"
        self._scenarios[prompt] = ModelScenario(kind)
        return prompt

    def scenario(self, prompt: str) -> ModelScenario:
        """查找当前运行创建的场景，不接受任意共享场景名称。"""
        return self._scenarios[prompt]

    def release_all(self) -> None:
        """释放所有等待中的模型调用，让服务退出能够完成真实资源清理。"""
        for scenario in self._scenarios.values():
            scenario.released.set()

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        """逐段生成受控回复，或沿用普通多轮与天气工具替身。

        门控场景先交付一段正文，再等待 fixture 显式释放；取消也会登记
        closed，供 E2E 确认浏览器断开确实传播到模型执行边界。
        """
        last = messages[-1]
        scenario = self._scenarios.get(last.content) if isinstance(last, HumanMessage) and isinstance(last.content, str) else None
        if scenario is None:
            async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                yield chunk
            return
        message_id = str(uuid4())
        scenario.started = True
        try:
            yield ChatGenerationChunk(message=AIMessageChunk(content="已收到部分回答", id=message_id))
            scenario.waiting.set()
            await scenario.released.wait()
            if scenario.kind == "fail":
                raise RuntimeError("本地模型模拟生成失败")
            yield ChatGenerationChunk(message=AIMessageChunk(content="，现在完成。", id=message_id))
        finally:
            scenario.closed = True


def build_test_app(settings, model: ControlledModel, control_token: str):
    """创建使用正式生命周期的测试应用，仅添加本地模型控制能力。

    settings 与模型 HTTP 边界的替换由启动器作用域负责恢复，不修改生产配置。
    控制路由要求本次运行生成的令牌，浏览器业务接口不经过替身。
    """
    from app.main import lifespan

    app = make_app(lifespan=lifespan)

    async def authorize(request: Request) -> None:
        """限制控制通道为持有本次临时令牌的测试 fixture 使用。"""
        if request.headers.get("authorization") != f"Bearer {control_token}":
            raise HTTPException(403)

    @app.post("/__e2e__/scenarios")
    async def prepare(request: Request):
        """为一个浏览器用例分配独立场景，返回可发送的提示文本。"""
        await authorize(request)
        body = await request.json()
        if body.get("kind") not in {"hold", "fail"}:
            raise HTTPException(422)
        return {"prompt": model.prepare(body["kind"])}

    @app.post("/__e2e__/scenarios/{prompt}/release")
    async def release(prompt: str, request: Request):
        """释放指定模型场景，不影响其他账号或并行测试。"""
        await authorize(request)
        try:
            model.scenario(prompt).released.set()
        except KeyError:
            raise HTTPException(404) from None
        return {"released": True}

    @app.get("/__e2e__/scenarios/{prompt}")
    async def status(prompt: str, request: Request):
        """公开指定场景的启动与清理状态，供测试进行条件等待。"""
        await authorize(request)
        try:
            scenario = model.scenario(prompt)
        except KeyError:
            raise HTTPException(404) from None
        return {"started": scenario.started, "closed": scenario.closed}

    return app


@asynccontextmanager
async def running_server(server, listener: socket.socket, model: ControlledModel) -> AsyncIterator[str]:
    """提供已就绪的回环服务，并在任何退出路径先释放模型再关闭服务器。"""
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(30):
            while not server.started:
                if task.done():
                    task.result()
                    raise RuntimeError("E2E 后端在就绪前退出")
                # 服务启动条件轮询，不用于模拟或断言用户操作的时序。
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    finally:
        model.release_all()
        server.should_exit = True
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=15)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            listener.close()


def forward_output(source: TextIO, target: TextIO) -> None:
    """将一条子进程输出流逐行交付父进程终端，并在结束时关闭读端。

    在独立工作线程中读取管道，打印后立即 flush；父进程输出可以是控制台、
    文件或 Python 捕获流，不要求它能提供可供子进程继承的操作系统句柄。
    """
    with source:
        for line in source:
            target.write(line)
            target.flush()


async def run_command(arguments: Sequence[str], environment: dict[str, str]) -> int:
    """运行项目 CLI 并透传输出，取消时回收本次启动的整个进程树。

    Windows Selector 循环通过工作线程等待同步进程，不依赖异步子进程。
    双输出流使用管道并发读取，再由 Python 转发；Windows 隐藏控制台时不依赖
    控制台句柄继承。结束或取消后等待读端完成，避免丢失尾部汇总或留下后台线程。
    强制回收只作用于本对象仍在运行的子进程，临时数据库由外层上下文回收。
    """
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
    # CREATE_NO_WINDOW 下直接继承原生控制台句柄仍可能丢失输出；管道与终端解耦。
    process = subprocess.Popen(
        list(arguments), cwd=FRONTEND_ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1, **options,
    )
    assert process.stdout is not None and process.stderr is not None
    readers = [
        asyncio.create_task(asyncio.to_thread(forward_output, process.stdout, sys.stdout)),
        asyncio.create_task(asyncio.to_thread(forward_output, process.stderr, sys.stderr)),
    ]
    try:
        result = await asyncio.to_thread(process.wait)
        await asyncio.gather(*(asyncio.shield(reader) for reader in readers))
        return result
    finally:
        try:
            if process.poll() is None:
                if sys.platform == "win32":
                    await asyncio.to_thread(subprocess.run, ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=10)
                except TimeoutError:
                    process.kill()
                    await asyncio.to_thread(process.wait)
        finally:
            # 取消等待不会取消读取任务；进程回收后读到 EOF，再完成本次命令的清理。
            await asyncio.gather(*(asyncio.shield(reader) for reader in readers), return_exceptions=True)


def reserve_listener() -> socket.socket:
    """绑定随机回环端口，后端直接接管该套接字，避免先探测再绑定的竞争。"""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    return listener


async def configure_test_model(settings) -> None:
    """通过正式配置服务在临时库中保存假密钥和默认模型，退出后关闭预备连接。"""
    async with open_business_database(settings) as database:
        service = ModelConfigService(database, settings.model_config_encryption_key)
        await seed_model_configuration(service)


async def run_e2e(arguments: Sequence[str]) -> int:
    """构建前端、创建临时库并执行浏览器测试，所有运行资源按依赖顺序退出。"""
    import app.main as main

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("E2E 需要项目要求版本的 Node.js")
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    built = await run_command([node, "node_modules/vite/bin/vite.js", "build"], environment)
    if built:
        return built
    async with temporary_database(load_database_settings(), on_created=report_database) as settings:
        await configure_test_model(settings)
        model = ControlledModel()
        token = secrets.token_urlsafe(32)
        app = build_test_app(settings, model, token)
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", log_level="warning", access_log=False, timeout_graceful_shutdown=10))
        @asynccontextmanager
        async def model_opener(snapshot):
            """保留配置快照和真实图，只替换付费模型调用边界。"""
            yield model

        with patch.object(main, "load_settings", return_value=settings), patch.object(main, "ConfiguredChatAgent", partial(ConfiguredChatAgent, model_opener=model_opener)):
            async with running_server(server, reserve_listener(), model) as api_url:
                with reserve_listener() as probe:
                    web_port = probe.getsockname()[1]
                environment.update({
                    "E2E_API_URL": api_url,
                    "E2E_CONTROL_TOKEN": token,
                    "E2E_WEB_PORT": str(web_port),
                    "E2E_BASE_URL": f"http://127.0.0.1:{web_port}",
                })
                result = await run_command([node, "node_modules/@playwright/test/cli.js", "test", *arguments], environment)
    print("E2E 服务与临时数据库已清理", flush=True)
    return result


def report_database(name: str) -> None:
    """在迁移前报告已创建的精确库名，强制终止后可据此确认残留目标。"""
    print(f"E2E 临时数据库：{name}；若进程被强制终止，请核对该库是否残留。", flush=True)


def main() -> None:
    """运行独立 E2E 生命周期并保留失败退出码，额外参数原样交给 Playwright。"""
    # 本地控制台与重定向日志统一 UTF-8，保证中文诊断和清理说明可读。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    arguments = sys.argv[1:]
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        raise SystemExit(runner.run(run_e2e(arguments)))


if __name__ == "__main__":
    main()
