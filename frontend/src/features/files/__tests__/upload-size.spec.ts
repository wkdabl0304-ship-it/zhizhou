/** 容量表单规则测试：验证单位、小数、边界和历史值回显不改变精确字节。 */
import { expect, it } from 'vitest'
import { editUploadSize, parseUploadSize, SIZE_UNITS } from '../upload-size'

it('常用上限以友好单位回显，小数按 1024 精确换算', () => {
  expect(editUploadSize(104857600)).toEqual({ value: '100', unit: 'MB' })
  expect(parseUploadSize('1.5', 'MB')).toBe(1572864)
  expect(parseUploadSize('1.2', 'MB')).toBe(1258291)
  expect(parseUploadSize(' 0.5 ', 'GB')).toBe(536870912)
  expect(parseUploadSize('1', 'TB')).toBe(1099511627776)
  expect(parseUploadSize('1', 'B')).toBe(1)
})

it('超限、非法数字及小于一个字节的容量不能保存', () => {
  for (const value of ['', '0', '-1', '1e3', 'NaN', '1,024', '1..5', '2']) {
    expect(parseUploadSize(value, 'TB')).toBeNull()
  }
  expect(parseUploadSize('0.1', 'B')).toBeNull()
  expect(parseUploadSize('0.0001', 'KB')).toBeNull()
})

it('历史策略使用简短自然单位，避免把冗长换算结果暴露给用户', () => {
  expect(editUploadSize(1048577)).toEqual({ value: '1', unit: 'MB' })
  expect(editUploadSize(1258291)).toEqual({ value: '1.2', unit: 'MB' })
  for (const unit of SIZE_UNITS) expect(parseUploadSize('1', unit)).not.toBeNull()
})
