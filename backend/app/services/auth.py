"""账号注册、密码校验和 JWT 生命周期；所有角色都使用同一所有权校验入口。"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from anyio import to_thread
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError

from app.core.settings import Settings
from app.db.business import BusinessDatabase
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError, RequestError
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
    """提供账号注册、登录和令牌认证服务。

    实例复用配置与密码工具，每次数据库操作独立创建 Session，
    不在服务对象中保存某个请求的事务或登录凭证。
    """

    def __init__(self, database: BusinessDatabase, settings: Settings) -> None:
        """初始化认证服务使用的数据库入口、配置和密码哈希工具。

        settings.jwt_secret 少于 32 字节时拒绝创建服务。这里只保存数据库
        工厂，不打开请求事务；登录前的占位密码摘要由 initialize 准备。
        """
        if len(settings.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET 至少需要 32 个字节")
        self.database = database
        self.settings = settings
        self.passwords = PasswordHash.recommended() # 创建密码哈希工具
        # 未知账号也执行一次密码校验，避免走明显不同的哈希计算路径。
        self._dummy_hash: str | None = None

    async def initialize(self) -> None:
        """为不存在账号的登录请求准备占位密码摘要。

        未知账号也会执行密码校验，避免与正常账号走明显不同的计算路径；
        哈希计算在线程池中执行，不阻塞异步服务的事件循环。
        """
        self._dummy_hash = await to_thread.run_sync( # hash 计算都放进线程池
            self.passwords.hash, "unused-account-password"
        )

    async def register(self, body: RegisterRequest) -> RegisteredUser:
        """注册新账号并返回不含密码摘要的账号信息。

        body 提供已校验的用户名、密码与角色。先在线程池计算密码摘要，
        再在短事务中创建账号；数据库唯一约束保证并发重名不会重复注册。
        用户名冲突转换为 USERNAME_EXISTS，其他数据库异常继续向外传播。
        """
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
        """验证登录信息并返回访问令牌、有效期和当前用户信息。

        body 提供用户名和密码，密码校验在线程池进行。账号不存在、已停用
        或密码错误统一抛出 INVALID_CREDENTIALS；成功后签发包含用户 ID、
        颁发时间、过期时间及签发方和接收方约束的 HS256 JWT。
        """
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
        """根据访问令牌取得当前仍可使用系统的用户。

        token 必须包含规定的 JWT 声明并通过签名、有效期及签发方和接收方
        校验；随后查询数据库中的最新账号状态，不只信任令牌本身。
        令牌无效、账号不存在或已停用时统一抛出 UNAUTHENTICATED。
        """
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
