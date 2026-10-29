"""账号注册、密码校验和 JWT 凭据版本生命周期；公开身份通过统一授权服务解析。"""

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
from app.repositories import files as file_repository
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisteredUser,
    RegisterRequest,
    UserInfo,
)
from app.services.authorization import AuthorizationService, management_lock


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
        self.authorization = AuthorizationService(database)
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

        body 提供已校验的用户名和密码。先在线程池计算密码摘要，
        再在短事务中创建账号；数据库唯一约束保证并发重名不会重复注册。
        用户名冲突转换为 USERNAME_EXISTS，其他数据库异常继续向外传播。
        """
        password_hash = await to_thread.run_sync(self.passwords.hash, body.password)
        try:
            async with self.database.sessions.begin() as session:
                user = await users.add_user(
                    session, body.username, password_hash
                )
                await self.authorization.bind(session, user, "user")
                # 空间与账号原子创建，注册失败时不会残留孤立空间。
                await file_repository.create_personal_space(session, user.id)
                info = await self.authorization.info(session, user)
                result = RegisteredUser(**info.model_dump(), created_at=user.created_at)
            return result
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise BusinessError(ErrorCode.USERNAME_EXISTS) from None
            raise

    async def login(self, body: LoginRequest) -> LoginResponse:
        """验证登录信息并返回访问令牌、有效期和当前用户信息。

        body 提供用户名和密码，密码校验在线程池进行。账号不存在或密码错误
        抛出 INVALID_CREDENTIALS；正确密码对应停用账号时抛出 ACCOUNT_DISABLED。
        成功后签发包含用户 ID、
        颁发时间、过期时间及签发方和接收方约束的 HS256 JWT。
        """
        async with self.database.sessions() as session:
            user = await users.by_username(session, body.username)
        if self._dummy_hash is None:
            await self.initialize()
        encoded = user.password_hash if user is not None else self._dummy_hash
        valid = await to_thread.run_sync(self.passwords.verify, body.password, encoded)
        if user is None or not valid:
            raise RequestError(ErrorCode.INVALID_CREDENTIALS)
        if not user.is_active:
            raise RequestError(ErrorCode.ACCOUNT_DISABLED)
        # 哈希校验不持事务；签发前取得共享管理锁，避免与改密或停用交错后签发旧凭据令牌。
        verified_hash, verified_version = user.password_hash, user.token_version
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            user = await users.by_id(session, user.id)
            if user is not None and not user.is_active:
                raise RequestError(ErrorCode.ACCOUNT_DISABLED)
            if user is None or user.password_hash != verified_hash or user.token_version != verified_version:
                raise RequestError(ErrorCode.INVALID_CREDENTIALS)
            info = await self.authorization.info(session, user)
            version = user.token_version
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.jwt_ttl_seconds),
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_audience,
                "token_version": version,
            },
            self.settings.jwt_secret,
            algorithm="HS256",
        )
        return LoginResponse(
            access_token=token,
            expires_in=self.settings.jwt_ttl_seconds,
            user=info,
        )

    async def authenticate(self, token: str) -> User:
        """根据访问令牌取得当前仍可使用系统的用户。

        token 必须包含规定的 JWT 声明并通过签名、有效期及签发方和接收方
        校验；随后查询数据库中的最新账号状态，不只信任令牌本身。
        令牌无效、凭据版本过期或账号不存在时抛出 UNAUTHENTICATED；停用账号单独提示。
        """
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={"require": ["sub", "iat", "exp", "iss", "aud", "token_version"]},
            )
            user_id = UUID(payload["sub"])
            if type(payload["token_version"]) is not int or payload["token_version"] < 1:
                raise ValueError("无效凭据版本")
        except jwt.InvalidTokenError, ValueError, TypeError, KeyError:
            raise RequestError(ErrorCode.UNAUTHENTICATED) from None
        async with self.database.sessions() as session:
            user = await users.by_id(session, user_id)
        if user is not None and not user.is_active:
            raise RequestError(ErrorCode.ACCOUNT_DISABLED)
        if user is None or user.token_version != payload["token_version"]:
            raise RequestError(ErrorCode.UNAUTHENTICATED)
        return user

    async def me(self, actor: User) -> UserInfo:
        """读取当前账号及其最新授权，使前端恢复身份时及时发现归属和角色变化。"""
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            user = await self.authorization.current(session, actor)
            return await self.authorization.info(session, user)
