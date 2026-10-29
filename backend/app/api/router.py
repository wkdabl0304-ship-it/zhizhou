"""API 总路由：统一声明 /api 前缀并集中注册各业务模块。

新增业务接口时在 routes 中定义子路由，再在此通过 include_router 注册。
main 模块只挂载本总路由，避免分散配置公共前缀或重复挂载接口。
"""

from fastapi import APIRouter

from app.api.routes import auth, chat, conversations, model_config, departments, users, files

api_router = APIRouter(prefix="/api")
# 子模块负责业务前缀；这里组合为 /api/chat，不重复声明 /api。
api_router.include_router(chat.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(model_config.router)
api_router.include_router(departments.router)
api_router.include_router(users.router)
api_router.include_router(files.router)
