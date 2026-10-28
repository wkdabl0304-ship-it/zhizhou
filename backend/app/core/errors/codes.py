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
    MODEL_AUTH_FAILED = (20002, "模型服务鉴权失败，请检查 API Key")
    MODEL_RATE_LIMITED = (20003, "模型服务限流或额度不足，请稍后重试")
    MODEL_TIMEOUT = (20004, "模型服务请求超时")
    MODEL_TEST_FAILED = (20005, "模型测试失败，请检查配置与模型访问权限")

    # 请求与协议错误：保留对应 HTTP 4xx。
    REQUEST_FAILED = (40000, "请求失败")
    UNAUTHENTICATED = (40101, "登录状态无效或已过期，请重新登录")
    INVALID_CREDENTIALS = (40102, "用户名或密码错误")
    FORBIDDEN = (40301, "没有执行此操作的权限")
    NOT_FOUND = (40400, "接口不存在")
    CONVERSATION_NOT_FOUND = (40401, "会话不存在或不可用")
    PROVIDER_CONFIGURATION_NOT_FOUND = (40402, "供应商配置不存在")
    MODEL_CONFIGURATION_NOT_FOUND = (40403, "模型配置不存在")
    USER_NOT_FOUND = (40404, "用户不存在")
    DEPARTMENT_NOT_FOUND = (40405, "部门不存在或不可用")
    CONVERSATION_BUSY = (40901, "会话正在生成，请稍后重试")
    MODEL_VERSION_CONFLICT = (40902, "模型配置已被修改，请刷新后重试")
    MODEL_CONFIG_IN_USE = (40903, "配置仍被引用，请先调整关联配置")
    MODEL_SELECTION_VERSION_CONFLICT = (40904, "会话模型选择已被修改，请刷新后重试")
    USER_IN_OTHER_DEPARTMENT = (40905, "用户已属于其他部门，请先移除原部门归属")
    LAST_SUPER_ADMIN = (40906, "必须保留至少一名可用超级管理员")
    TARGET_STATE_CONFLICT = (40907, "目标状态或归属已变化，请刷新后重试")
    DEPARTMENT_NAME_EXISTS = (40908, "部门名称已存在")
    METHOD_NOT_ALLOWED = (40500, "请求方法不允许")
    INVALID_ARGUMENT = (42200, "请求参数校验失败")
    MODEL_SELECTION_UNAVAILABLE = (42201, "选择的模型已删除、停用或不可用，请重新选择")
    REASONING_NOT_ALLOWED = (42202, "推理值不符合当前限制，请重新选择")

    # 系统失败：HTTP 5xx。
    INTERNAL_ERROR = (50000, "服务器内部错误，请稍后重试")
    CHAT_FAILED = (50001, "对话执行失败，请稍后重试")
    TOOL_FAILED = (50002, "工具执行失败")
    MODEL_PROVIDER_FAILED = (50003, "模型服务调用失败")
    MODEL_NOT_CONFIGURED = (50301, "尚未选择可用模型，请选择模型或配置有效默认")

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
