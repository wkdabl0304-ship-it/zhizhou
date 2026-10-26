"""模型配置 ORM：供应商配置、可复用模型设置与单例默认引用，不存储内置模型目录。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.entities import Base


class ProviderConfiguration(Base):
    """官方供应商配置；密钥只能由服务层加密写入，公开响应使用独立字段白名单。"""

    __tablename__ = "provider_configurations"
    # UPDATE 时用 RETURNING 取回数据库时间，避免异步响应序列化触发隐式查询。
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("provider IN ('openai', 'anthropic', 'deepseek', 'bailian')", name="ck_provider_configurations_provider"),
        CheckConstraint("(provider = 'openai' AND api_format IN ('responses', 'chat_completions')) OR (provider = 'anthropic' AND api_format = 'messages') OR (provider IN ('deepseek', 'bailian') AND api_format = 'chat_completions')", name="ck_provider_configurations_format"),
        CheckConstraint("version > 0 AND credential_revision > 0", name="ck_provider_configurations_versions"),
        CheckConstraint("jsonb_typeof(endpoint_config) = 'object'", name="ck_provider_configurations_endpoint"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    provider: Mapped[str] = mapped_column(String(20))
    api_format: Mapped[str] = mapped_column(String(30))
    endpoint_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    api_key_ciphertext: Mapped[str] = mapped_column(Text)
    credential_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ModelConfiguration(Base):
    """绑定供应商配置与内置模型的用户配置，同一模型可以保存多个推理方案。"""

    __tablename__ = "model_configurations"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("version > 0 AND max_output_tokens > 0", name="ck_model_configurations_limits"),
        CheckConstraint("jsonb_typeof(reasoning) = 'object'", name="ck_model_configurations_reasoning"),
        CheckConstraint("jsonb_typeof(reasoning_policy) = 'object' AND coalesce(reasoning_policy ->> 'mode' IN ('fixed', 'selectable'), false)", name="ck_model_configurations_reasoning_policy"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider_configuration_id: Mapped[UUID] = mapped_column(ForeignKey("provider_configurations.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    catalog_model_id: Mapped[str] = mapped_column(String(160))
    reasoning: Mapped[dict[str, Any]] = mapped_column(JSONB)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # 每个新方案取得独立固定策略字典，避免 ORM 默认值在实例之间共享可变对象。
    reasoning_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: {"mode": "fixed"}, server_default=text("'{\"mode\":\"fixed\"}'::jsonb"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=16384, server_default="16384")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatModelSettings(Base):
    """全局唯一的默认引用，同时充当配置写入的事务锁，版本用于防止覆盖。"""

    __tablename__ = "chat_model_settings"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_chat_model_settings_singleton"),
        CheckConstraint("version > 0", name="ck_chat_model_settings_version"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    model_configuration_id: Mapped[UUID | None] = mapped_column(ForeignKey("model_configurations.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
