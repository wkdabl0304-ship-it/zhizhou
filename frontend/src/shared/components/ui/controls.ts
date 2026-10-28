/** 基础表单控件公开类型：选项内容由业务模块提供，公共组件不维护业务枚举。 */
export interface UiSelectOption {
  value: string
  label: string
  disabled?: boolean
}
