"""供应商客户端装配：优先专用 LangChain 包，每个执行上下文拥有独立 HTTP 资源。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from functools import cached_property

import anthropic
import anyio
import httpx
import httpx2
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen
from pydantic import PrivateAttr

from app.llm.providers.deepseek import DeepSeekChatModel
from app.llm.providers.failures import ProviderFailure, SafeStreamMixin, classify_failure
from app.llm.types import ModelSnapshot


class OpenAIChatModel(SafeStreamMixin, ChatOpenAI):
    """保留 OpenAI 原生 Responses 与 Chat 能力，只增加安全错误边界。"""


class QwenChatModel(SafeStreamMixin, ChatQwen):
    """复用百炼 Qwen 原生思考、流式及工具解析，只增加安全错误边界。"""


class AnthropicChatModel(SafeStreamMixin, ChatAnthropic):
    """使 Anthropic 使用本轮拥有的 HTTP 客户端，避免关闭包内跨请求缓存。"""

    _owned_sync: httpx2.Client = PrivateAttr()
    _owned_async: httpx2.AsyncClient = PrivateAttr()

    def attach_http(self, sync: httpx2.Client, asynchronous: httpx2.AsyncClient) -> None:
        """在首次使用 SDK 前注入本轮客户端，生命周期由供应商上下文统一管理。"""
        self._owned_sync, self._owned_async = sync, asynchronous

    @cached_property
    def _client(self) -> anthropic.Client:
        """创建同步 SDK 包装器，沿用专用包参数而不使用其全局 HTTP 缓存。"""
        return anthropic.Client(**self._client_params, http_client=self._owned_sync)

    @cached_property
    def _async_client(self) -> anthropic.AsyncClient:
        """创建异步 SDK 包装器，保留原生 Messages 流和工具事件解析。"""
        return anthropic.AsyncClient(**self._client_params, http_client=self._owned_async)


@asynccontextmanager
async def open_model(
    snapshot: ModelSnapshot, *, transport: httpx.AsyncBaseTransport | httpx2.AsyncBaseTransport | None = None,
    sync_transport: httpx.BaseTransport | httpx2.BaseTransport | None = None,
) -> AsyncIterator[BaseChatModel]:
    """为一次执行提供专用模型客户端，退出或取消时关闭本轮全部 HTTP 资源。

    transport 只用于协议测试注入模拟 HTTP；地址和密钥来自已校验的快照，
    不使用供应商环境变量回退。构造失败也在 finally 中清理已创建的资源。
    """
    # 锁定的 Anthropic SDK 使用 httpx2，OpenAI 系列 SDK 使用 httpx；不可混用客户端类型。
    http = httpx2 if snapshot.provider == "anthropic" else httpx
    sync = None
    asynchronous = None
    try:
        try:
            sync = http.Client(transport=sync_transport, timeout=120, follow_redirects=False)
            asynchronous = http.AsyncClient(transport=transport, timeout=120, follow_redirects=False)
            params = deepcopy(snapshot.parameters)
            params.update(api_key=snapshot.api_key, base_url=snapshot.base_url, max_retries=0, timeout=120)
            if snapshot.provider == "anthropic":
                model = AnthropicChatModel(**params)
                model.attach_http(sync, asynchronous)
            else:
                params.update(http_client=sync, http_async_client=asynchronous)
                client = {"openai": OpenAIChatModel, "deepseek": DeepSeekChatModel, "bailian": QwenChatModel}[snapshot.provider]
                model = client(**params)
        except Exception as error:
            raise ProviderFailure(classify_failure(error)) from None
        yield model
    finally:
        # 断开取消不能中断连接池清理；包内 SDK 包装器不拥有额外连接池。
        with anyio.CancelScope(shield=True):
            try:
                if asynchronous is not None:
                    await asynchronous.aclose()
            finally:
                if sync is not None:
                    sync.close()
