/** 模型身份契约回归：新旧响应兼容，公开字段严格投影，损坏身份不进入历史。 */
import { expect, it } from 'vitest'
import { decodeModelIdentity } from '../identity'

it('缺失身份兼容旧响应，完整身份只保留公开白名单', () => {
  expect(decodeModelIdentity(undefined)).toBeNull()
  expect(decodeModelIdentity(null)).toBeNull()
  const identity = {
    model_configuration_id: 'model',
    catalog_model_id: 'provider:model',
    display_name: '模型',
  }
  expect(decodeModelIdentity({ ...identity, parameters: { api_key: 'private' } })).toEqual(identity)
})

it.each([
  [],
  'model',
  {},
  { model_configuration_id: 'x', catalog_model_id: 'y', display_name: '' },
])('损坏身份不能伪装成有效模型 %#', (value) => {
  expect(() => decodeModelIdentity(value)).toThrow('模型身份格式无效')
})
