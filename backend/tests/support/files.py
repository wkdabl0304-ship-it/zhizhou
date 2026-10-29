"""文件测试共享请求辅助；全部数据通过正式 API 创建，只使用本例随机库和临时磁盘。"""

from uuid import UUID


async def spaces(runtime, headers):
    """取得当前账号的全部可见空间，测试数据规模保持在单页内。"""
    response = await runtime.client.get("/api/files/spaces", headers=headers, params={"limit": 100})
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


async def space(runtime, headers, kind, department_id=None):
    """定位测试目标空间，不通过内部主键推测空间标识。"""
    return next(row for row in await spaces(runtime, headers) if row["kind"] == kind
                and (department_id is None or row["department_id"] == str(department_id)))


async def folder(runtime, headers, space_id, name="资料", parent_id=None):
    """在指定目录调用正式创建接口，返回包含乐观版本的条目。"""
    response = await runtime.client.post(f"/api/files/spaces/{space_id}/folders", headers=headers,
                                         json={"name": name, "parent_id": parent_id})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def upload(runtime, headers, space_id, name="方案.pdf", content=b"\x00\xfforiginal", parent_id=None):
    """上传任意原始字节并返回元数据，由调用场景决定是否允许重名。"""
    response = await runtime.client.post(f"/api/files/spaces/{space_id}/files", headers=headers,
        params={"parent_id": parent_id} if parent_id else None, files={"file": (name, content, "application/octet-stream")})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def department(runtime, headers, name="研发部", manager=None):
    """创建部门，并可选通过正式成员及任免接口配置部门管理员。"""
    response = await runtime.client.post("/api/departments", headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    department_id = response.json()["data"]["id"]
    if manager is not None:
        await join(runtime, headers, department_id, manager)
        response = await runtime.client.put(f"/api/departments/{department_id}/administrators/{manager.id}", headers=headers)
        assert response.status_code == 200, response.text
    return department_id


async def join(runtime, headers, department_id, user):
    """通过正式接口加入已注册成员，不直接写用户归属或角色表。"""
    response = await runtime.client.post(f"/api/departments/{department_id}/members", headers=headers,
                                        json={"username": user.username})
    assert response.status_code == 200, response.text


async def actor(runtime, headers):
    """为服务级并发测试取得与真实请求相同的认证身份。"""
    return await runtime.auth.authenticate(headers["Authorization"].removeprefix("Bearer "))


async def blob_for(runtime, entry_id):
    """查询本例文件原件供磁盘和生命周期断言，不参与被测权限决策。"""
    from app.models import FileBlob, FileEntry
    async with runtime.database.sessions() as session:
        entry = await session.get(FileEntry, UUID(str(entry_id)))
        return await session.get(FileBlob, entry.blob_id)
