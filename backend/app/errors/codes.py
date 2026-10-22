"""响应码与客户端解释的唯一维护位置。新增业务码使用 20000–29999。"""

from enum import Enum, unique


@unique
class ErrorCode(Enum):
    """通过符号名称绑定整数码与客户端解释，避免两份映射各自维护。"""

    # 成功
    SUCCESS = (0, "成功")

    # 业务失败：HTTP 200。按实际功能增加条目，不复用已有码值。
    BUSINESS_ERROR = (20000, "业务处理失败")
    USERNAME_EXISTS = (20001, "用户名已存在")

    # 请求与协议错误：保留对应 HTTP 4xx。
    REQUEST_FAILED = (40000, "请求失败")
    UNAUTHENTICATED = (40101, "登录状态无效或已过期，请重新登录")
    INVALID_CREDENTIALS = (40102, "用户名或密码错误")
    NOT_FOUND = (40400, "接口不存在")
    CONVERSATION_NOT_FOUND = (40401, "会话不存在或不可用")
    CONVERSATION_BUSY = (40901, "会话正在生成，请稍后重试")
    METHOD_NOT_ALLOWED = (40500, "请求方法不允许")
    INVALID_ARGUMENT = (42200, "请求参数校验失败")

    # 系统失败：HTTP 5xx。
    INTERNAL_ERROR = (50000, "服务器内部错误，请稍后重试")
    CHAT_FAILED = (50001, "对话执行失败，请稍后重试")
    TOOL_FAILED = (50002, "工具执行失败")

    @property
    def code(self) -> int:
        """返回写入 JSON code 字段的整数，不直接序列化枚举对象。"""
        return self.value[0]

    @property
    def message(self) -> str:
        """返回可展示给客户端的固定解释，不包含底层异常细节。"""
        return self.value[1]

    @property
    def is_business(self) -> bool:
        """判断码值是否属于约定的业务区间，供异常构造函数校验。"""
        return 20000 <= self.code <= 29999
