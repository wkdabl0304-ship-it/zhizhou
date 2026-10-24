"""模型凭据加密：部署主密钥与数据库分离，解密内容只存在于当前运行快照。"""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr


class SecretBox:
    """使用认证加密保存 API Key，不将主密钥放入实体或可打印属性。"""

    def __init__(self, key: str):
        """校验部署主密钥并创建加解密器，错误不包含原始输入。"""
        try:
            self._cipher = Fernet(key.encode("ascii"))
        except (ValueError, UnicodeError):
            raise ValueError("模型配置加密主密钥无效") from None

    def encrypt(self, value: SecretStr) -> str:
        """把非空 API Key 加密为可存储文本，不改变模型凭据内容。"""
        plain = value.get_secret_value()
        if not plain.strip():
            raise ValueError("API Key 不能为空")
        return self._cipher.encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> SecretStr:
        """解密已存凭据，主密钥不匹配或密文损坏时抛出安全错误。"""
        try:
            return SecretStr(self._cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError):
            raise ValueError("模型凭据无法解密，请检查部署主密钥") from None
