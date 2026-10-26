"""模型配置仓储：执行 ORM 查询，配置写事务及版本校验由服务层组织。"""

from uuid import UUID

from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatModelSettings, ModelConfiguration, ProviderConfiguration


async def settings(session: AsyncSession, *, lock: bool = False) -> ChatModelSettings:
    """取得默认设置单例，写入时锁定此行以序列化全部配置关联变更。"""
    query = select(ChatModelSettings).where(ChatModelSettings.id == 1)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise RuntimeError("模型设置单例缺失，请检查数据库迁移")
    return row


async def provider_configuration(session: AsyncSession, provider_configuration_id: UUID) -> ProviderConfiguration | None:
    """读取供应商配置；是否存在和允许修改由服务层判断。"""
    return await session.get(ProviderConfiguration, provider_configuration_id)


async def provider_configurations(session: AsyncSession) -> list[ProviderConfiguration]:
    """按创建顺序读取全局供应商配置，配置规模较小，首期不引入分页。"""
    return list(await session.scalars(select(ProviderConfiguration).order_by(ProviderConfiguration.created_at, ProviderConfiguration.id)))


async def model_rows(session: AsyncSession, provider_configuration_id: UUID | None = None):
    """一次联表读取模型配置与供应商配置，避免目录展示时逐条查询供应商配置格式。"""
    query = select(ModelConfiguration, ProviderConfiguration).join(ProviderConfiguration)
    if provider_configuration_id is not None:
        query = query.where(ModelConfiguration.provider_configuration_id == provider_configuration_id)
    return (await session.execute(query.order_by(ModelConfiguration.created_at, ModelConfiguration.id))).all()


async def model_row(session: AsyncSession, model_id: UUID):
    """一次联表读取指定模型及供应商配置，保证版本、密钥和参数来自同一语句快照。"""
    return (await session.execute(select(ModelConfiguration, ProviderConfiguration).join(ProviderConfiguration)
                                  .where(ModelConfiguration.id == model_id))).first()


async def default_row(session: AsyncSession):
    """一次外联表读取全局默认及关联配置，未设置默认时仍返回单例。"""
    return (await session.execute(select(ChatModelSettings, ModelConfiguration, ProviderConfiguration)
                                  .outerjoin(ModelConfiguration, ChatModelSettings.model_configuration_id == ModelConfiguration.id)
                                  .outerjoin(ProviderConfiguration, ModelConfiguration.provider_configuration_id == ProviderConfiguration.id)
                                  .where(ChatModelSettings.id == 1))).one()


async def option_rows(session: AsyncSession):
    """在同一 SQL 快照读取默认引用及所有方案，空配置时也保留设置单例。"""
    query = (select(ChatModelSettings, ModelConfiguration, ProviderConfiguration)
             .select_from(ChatModelSettings)
             .outerjoin(ModelConfiguration, true())
             .outerjoin(ProviderConfiguration, ModelConfiguration.provider_configuration_id == ProviderConfiguration.id)
             .where(ChatModelSettings.id == 1)
             .order_by(ProviderConfiguration.created_at, ProviderConfiguration.id, ModelConfiguration.created_at, ModelConfiguration.id))
    return (await session.execute(query)).all()


async def selected_model_rows(session: AsyncSession, ids: set[UUID]):
    """批量读取会话选择涉及的方案，避免会话目录产生逐条配置查询。"""
    if not ids:
        return []
    return (await session.execute(select(ModelConfiguration, ProviderConfiguration).join(ProviderConfiguration)
                                  .where(ModelConfiguration.id.in_(ids)))).all()
