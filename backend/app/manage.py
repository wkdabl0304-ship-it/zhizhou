"""本地运维入口：为已注册且启用的账号授予超管，不提供免认证 HTTP 初始化通道。"""

import argparse
import asyncio
from collections.abc import Sequence

from app.core.event_loop import create_event_loop
from app.core.errors.exceptions import AppError
from app.core.settings import load_settings
from app.db.business import open_business_database
from app.schemas.identifiers import normalize_username
from app.services.users import grant_super_admin


async def grant(username: str) -> None:
    """连接当前已迁移数据库，为运维指定账号授予全局管理角色，退出释放引擎。"""
    async with open_business_database(load_settings()) as database:
        await grant_super_admin(database, username)


def main(argv: Sequence[str] | None = None) -> None:
    """解析明确的运维命令；失败返回非零退出码，不回显凭据或数据库连接地址。"""
    parser = argparse.ArgumentParser(description="知舟本地账号运维")
    subcommands = parser.add_subparsers(dest="command", required=True)
    command = subcommands.add_parser("grant-super-admin", help="授予已注册启用账号超级管理员")
    command.add_argument("username", help="完整用户名")
    args = parser.parse_args(argv)
    try:
        username = normalize_username(args.username)
        with asyncio.Runner(loop_factory=create_event_loop) as runner:
            runner.run(grant(username))
    except AppError as error:
        parser.exit(1, f"操作失败：{error.error_code.message}\n")
    except ValueError:
        parser.error("用户名或运行配置无效，请检查账号格式与配置")
    print(f"已授予超级管理员：{username}")


if __name__ == "__main__":
    main()
