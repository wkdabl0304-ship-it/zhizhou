# 知舟后端

使用 Python 3.14 及以上版本和 uv 管理后端项目，已声明 FastAPI 依赖。当前仅有目录骨架，`app/main.py` 为空，尚未创建 FastAPI 应用，也没有可启动的 API 服务。

项目定位和功能规划见[根 README](../README.md)。

## 开发命令

在 `backend/` 目录执行：

```powershell
uv sync
uv add <包名>
uv add --dev <包名>
uv build
```

使用 `uv run <命令>` 在项目虚拟环境中执行命令。提交 `pyproject.toml`、`uv.lock` 和 `.python-version`；不提交 `.venv/`、本地环境变量及构建产物。

## 目录职责

- `app/main.py`：应用入口，待实现。
- `app/api/`：HTTP 接口。
- `app/config/`：配置相关代码，当前为包占位。
- `app/db/`：数据库连接和会话。
- `app/models/`：数据库模型。
- `app/schemas/`：请求和响应的数据结构。
- `app/repositories/`：数据库查询和写入。
- `app/services/`：业务流程和规则。
- `app/utils/`：不含业务规则的通用辅助函数。
- `tests/`：后端测试，按功能添加。

后续开发智能体和外部服务接入时，再添加 `app/agent/` 与 `app/integrations/`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
