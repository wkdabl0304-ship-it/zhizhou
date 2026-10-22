"""账号注册、密码校验和 JWT 生命周期；所有角色都使用同一所有权校验入口。"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from anyio import to_thread
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.business import BusinessDatabase
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError, RequestError
from app.models import User
from app.repositories import users
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisteredUser,
    RegisterRequest,
    UserInfo,
)


class AuthService:
    """共享配置与线程安全的密码工具；不保存请求 Session 或登录凭证。"""

    def __init__(self, database: BusinessDatabase, settings: Settings) -> None:
        """校验签名密钥，初始化哈希器；实际数据库操作按请求创建独立 Session。"""
        if len(settings.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET 至少需要 32 个字节")
        self.database = database
        self.settings = settings
        self.passwords = PasswordHash.recommended() # 创建密码哈希工具
        # 未知账号也执行一次密码校验，避免走明显不同的哈希计算路径。
        self._dummy_hash: str | None = None

    async def initialize(self) -> None:
        """在线程池准备未知账号的校验摘要，避免启动和登录阻塞事件循环。"""
        self._dummy_hash = await to_thread.run_sync( # hash 计算都放进线程池
            self.passwords.hash, "unused-account-password"
        )

    async def register(self, body: RegisterRequest) -> RegisteredUser:
        """哈希后通过唯一约束原子注册；并发重名只返回安全业务错误。"""
        password_hash = await to_thread.run_sync(self.passwords.hash, body.password)
        try:
            async with self.database.sessions.begin() as session:
                user = await users.add_user(
                    session, body.username, password_hash, body.role
                )
                result = RegisteredUser.model_validate(user)
            return result
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise BusinessError(ErrorCode.USERNAME_EXISTS) from None
            raise

    async def login(self, body: LoginRequest) -> LoginResponse:
        """校验账号与密码后签发访问令牌；错误不区分账号不存在、停用或密码错误。"""
        async with self.database.sessions() as session:
            user = await users.by_username(session, body.username)
        if self._dummy_hash is None:
            await self.initialize()
        encoded = user.password_hash if user is not None else self._dummy_hash
        valid = await to_thread.run_sync(self.passwords.verify, body.password, encoded)
        if user is None or not valid or not user.is_active:
            raise RequestError(ErrorCode.INVALID_CREDENTIALS)
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.jwt_ttl_seconds),
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
            },
            self.settings.jwt_secret,
            algorithm="HS256",
        )
        return LoginResponse(
            access_token=token,
            expires_in=self.settings.jwt_ttl_seconds,
            user=UserInfo.model_validate(user),
        )

    async def authenticate(self, token: str) -> User:
        """验证必需声明、签名和数据库账号状态，拒绝过期或无法归属的令牌。"""
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["sub", "iat", "exp", "iss", "aud"]},
            )
            user_id = UUID(payload["sub"])
        except jwt.InvalidTokenError, ValueError, TypeError, KeyError:
            raise RequestError(ErrorCode.UNAUTHENTICATED) from None
        async with self.database.sessions() as session:
            user = await users.by_id(session, user_id)
        if user is None or not user.is_active:
            raise RequestError(ErrorCode.UNAUTHENTICATED)
        return user
