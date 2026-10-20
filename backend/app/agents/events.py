"""Agent 过程事件适配：捕获工具的真实执行生命周期。

工具回调通过 LangGraph custom 通道发送结构化数据，与正文共享同一条流。
每轮创建独立回调实例，避免不同会话间的工具状态串写；不发送内部异常、
完整框架对象或工具 artifact，也不将这些过程正文主动写入应用日志。
"""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer

from app.errors.codes import ErrorCode
from app.schemas.chat import ChatToolEnd, ChatToolError, ChatToolStart


@dataclass
class _ToolRun:
    """一次工具运行的最小上下文，用于关联开始与终止事件。"""

    tool_call_id: str
    name: str
    kind: Literal["tool", "command"]


class ToolEventHandler(AsyncCallbackHandler):
    """将真实工具回调写入当前图的 custom 流；实例只属于本轮执行。"""

    # 内联执行确保开始事件先于工具体；适配失败时交给 Agent 的统一异常边界。
    run_inline = True
    raise_error = True

    def __init__(self, thread_id: str) -> None:
        """保存会话标识，创建按运行 ID 区分的并行工具上下文。"""
        self._thread_id = thread_id
        self._runs: dict[UUID, _ToolRun] = {}

    async def on_tool_start(
        self, serialized: dict[str, Any] | None, input_str: str, *,
        run_id: UUID, inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None, **kwargs: Any,
    ) -> None:
        """在工具实际执行前发送名称和公开参数；框架已过滤注入参数。

        命令工具可声明 metadata.display_kind=command；没有声明则作为普通工具。
        无模型调用标识的嵌套工具以 run_id 作为独立标识，避免与其他运行混淆。
        """
        kind = "command" if (metadata or {}).get("display_kind") == "command" else "tool"
        run = _ToolRun(
            tool_call_id=kwargs.get("tool_call_id") or str(run_id),
            name=(serialized or {}).get("name") or kwargs.get("name") or "tool",
            kind=kind,
        )
        self._runs[run_id] = run
        get_stream_writer()(ChatToolStart( # 往 custom 流里写入事件
            thread_id=self._thread_id, tool_call_id=run.tool_call_id,
            run_id=str(run_id), name=run.name, kind=run.kind,
            arguments=inputs if inputs is not None else input_str,
        ))

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        """发送工具正文或可恢复的工具错误，不暴露 artifact 和工具对象表示。"""
        run = self._runs.pop(run_id, None)
        if run is None:
            return
        if isinstance(output, ToolMessage) and output.status == "error": # 处理 ToolMessage 格式的错误
            self._write_error(run_id, run)
            return
        content = output.content if isinstance(output, ToolMessage) else output
        get_stream_writer()(ChatToolEnd(
            thread_id=self._thread_id, tool_call_id=run.tool_call_id,
            run_id=str(run_id), name=run.name, kind=run.kind, output=content,
        ))

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None: # 处理 raise 出来的错误
        """报告真实执行失败；底层异常及异常链交给 Agent 日志和错误分类处理。"""
        run = self._runs.pop(run_id, None)
        if run is not None:
            self._write_error(run_id, run)

    def _write_error(self, run_id: UUID, run: _ToolRun) -> None:
        """统一编码安全工具失败事件，不把异常字符串混入客户端过程流。"""
        get_stream_writer()(ChatToolError(
            thread_id=self._thread_id, tool_call_id=run.tool_call_id,
            run_id=str(run_id), name=run.name, kind=run.kind,
            message=ErrorCode.TOOL_FAILED.message,
        ))
