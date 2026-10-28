"""PostgreSQL 集成测试：独立临时库验证认证、JWT 和账号状态。"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import update

from app.core.errors.codes import ErrorCode
from app.models import User
from app.schemas.auth import RegisterRequest
from tests.support.postgres import open_runtime as runtime

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_register_login_jwt_claims_and_disabled_account(postgres_settings):
    """验证普通账号的注册登录、拒绝公开提权，以及真实 JWT 的认证边界。

    覆盖必需声明、有效期、签名算法、凭据版本类型与边界和账号停用状态，测试账号仅写入隔离库。
    """

    async with runtime(postgres_settings) as environment:
        database = environment.database
        client = environment.client
        username = "http_" + uuid4().hex[:20]
        body = {
            "username": " " + username.upper() + " ",
            "password": "password-123",
            "role": "user",
        }
        response = await client.post("/api/auth/register", json=body)
        assert response.status_code == 200 and response.json()["code"] == 0
        assert response.json()["data"]["role"] == "user"
        rejected = await client.post("/api/auth/register", json={**body, "username": "forbidden_admin", "role": "super_admin"})
        assert rejected.status_code == 422
        assert response.json()["data"]["roles"] == ["user"]
        assert "password" not in response.text
        assert (await client.post("/api/auth/register", json=body)).json()[
            "code"
        ] == 20001
        logged = await client.post(
            "/api/auth/login",
            json={"username": username, "password": "password-123"},
        )
        data = logged.json()["data"]
        assert data["expires_in"] == 7200 and data["token_type"] == "bearer"
        headers = {"Authorization": "Bearer " + data["access_token"]}
        assert (await client.get("/api/auth/me", headers=headers)).json()["data"][
            "username"
        ] == username
        for path in ["/api/auth/me", "/api/conversations"]:
            denied = await client.get(path)
            assert (
                denied.status_code == 401
                and denied.headers["www-authenticate"] == "Bearer"
            )
        for login_body in [
            {"username": username, "password": "wrong-password"},
            {
                "username": "missing_" + uuid4().hex[:15],
                "password": "wrong-password",
            },
        ]:
            denied = await client.post("/api/auth/login", json=login_body)
            assert denied.status_code == 401 and denied.json()["code"] == 40102
        now = datetime.now(UTC)
        payload = {
            "sub": data["user"]["id"],
            "iat": now,
            "exp": now + timedelta(hours=1),
            "iss": "zhizhou",
            "aud": "zhizhou-api",
            "token_version": 1,
        }
        bad_claims = [
            {**payload, "exp": now - timedelta(seconds=1)},
            {**payload, "aud": "other"},
            {**payload, "iss": "other"},
            {**payload, "sub": "not-a-uuid"},
            {key: value for key, value in payload.items() if key != "exp"},
        ]
        # 凭据版本只接受正整数，布尔值不能因 Python 中 True == 1 而被当作版本 1。
        bad_claims.extend(
            {**payload, "token_version": value}
            for value in (None, True, False, 0, -1, "1", 1.5)
        )
        tokens = [
            jwt.encode(claims, postgres_settings.jwt_secret, algorithm="HS256")
            for claims in bad_claims
        ]
        tokens.extend(
            [
                jwt.encode(
                    payload, "different-secret-at-least-32-bytes", algorithm="HS256"
                ),
                jwt.encode(
                    payload, postgres_settings.jwt_secret, algorithm="HS384"
                ),
                "broken-token",
            ]
        )
        for token in tokens:
            assert (
                await client.get(
                    "/api/auth/me", headers={"Authorization": "Bearer " + token}
                )
            ).status_code == 401
        async with database.sessions.begin() as session:
            await session.execute(
                update(User)
                .where(User.username == username)
                .values(is_active=False)
            )
        assert (
            await client.get("/api/auth/me", headers=headers)
        ).status_code == 401
        assert (
            await client.post(
                "/api/auth/login",
                json={"username": username, "password": "password-123"},
            )
        ).status_code == 401


@pytest.mark.anyio
async def test_concurrent_registration_has_one_winner(postgres_settings):
    """验证同名账号并发注册仅一个成功，另一个返回重名业务错误。"""
    async with runtime(postgres_settings) as environment:
        auth = environment.auth
        username = "race_" + uuid4().hex[:20]
        results = await asyncio.gather(
            *(
                auth.register(
                    RegisterRequest(username=username, password="password-123")
                )
                for _ in range(2)
            ),
            return_exceptions=True,
        )
        assert sum(not isinstance(result, Exception) for result in results) == 1
        assert (
            sum(
                getattr(result, "error_code", None) is ErrorCode.USERNAME_EXISTS
                for result in results
            )
            == 1
        )
