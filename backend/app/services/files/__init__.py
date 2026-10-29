"""共享文件业务模块；公开 FileService，内部拆分授权、传输、策略和清理职责。"""

from app.services.files.service import FileService

__all__ = ["FileService"]
