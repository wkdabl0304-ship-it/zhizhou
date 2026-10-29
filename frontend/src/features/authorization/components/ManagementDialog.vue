<!-- 组织管理操作弹窗：固定资源、解释操作后果，密码仅在当前表单和一次请求中存在。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import { computed, onBeforeUnmount, ref } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import { useAuthStore } from '@/features/auth/store'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
import { execute } from '../api'
import { canPerformAction } from '../access'
import type { ManagementAction } from '../types'

const props = defineProps<{ action: ManagementAction }>()
const auth = useAuthStore()
const emit = defineEmits<{ close: []; saved: []; conflict: [] }>()
const busy = ref(false),
  error = ref(''),
  attempted = ref(false)
const input = ref(props.action.kind === 'rename-department' ? props.action.department.name : '')
const controller = new AbortController()
const definitions = {
  'create-department': ['新建部门', '为团队建立一个清晰的协作归属。', '创建部门'],
  'rename-department': ['重命名部门', '修改显示名称，成员归属与管理权限保持不变。', '保存名称'],
  'delete-department': [
    '删除部门',
    '所有成员将变为无部门，部门管理员权限一并撤销。账号、全局角色与个人会话保留，此操作无法撤销。',
    '删除部门',
  ],
  'add-member': [
    '加入成员',
    '输入已有账号的完整用户名，立即加入本部门。账号必须已启用且尚未属于其他部门。',
    '加入部门',
  ],
  'remove-member': [
    '移出部门',
    '移除成员归属，并撤销其在本部门绑定的管理权限。账号、全局角色和个人内容保留。',
    '移出部门',
  ],
  'assign-department-admin': [
    '设为部门管理员',
    '允许此成员查看本部门，并加入或移出成员。不会获得全站账号、模型配置或他人会话权限。',
    '授予权限',
  ],
  'revoke-department-admin': [
    '撤销部门管理员',
    '仅撤销本部门的管理权限，成员仍保留在本部门。',
    '撤销权限',
  ],
  'enable-user': ['启用账号', '允许此账号重新登录。已失效的旧令牌不会恢复。', '启用账号'],
  'disable-user': [
    '停用账号',
    '此账号将无法登录，所有旧令牌失效。部门、角色和个人内容保留；已经开始的生成允许完成。',
    '停用账号',
  ],
  'reset-password': [
    '重置密码',
    '直接设置新密码并使全部旧令牌失效。管理员可使用新密码登录该账号，请妥善交付。',
    '重置密码',
  ],
  'assign-super-admin': [
    '授予超级管理员',
    '允许此账号管理全站账号、部门、角色和模型配置。其本人会话权限仍只覆盖自己。',
    '授予权限',
  ],
  'revoke-super-admin': [
    '撤销超级管理员',
    '撤销全站管理权限，保留基础角色及部门身份。系统必须保留至少一名启用的超级管理员。',
    '撤销权限',
  ],
} as const
const definition = computed(() => definitions[props.action.kind])
// 只有依赖部门绑定的操作者移除本人时失去本部门管理入口；全局授权不受影响。
const description = computed(
  () =>
    definition.value[1] +
    (props.action.kind === 'remove-member' &&
    props.action.member.id === auth.user?.id &&
    !auth.can('department_member:read')
      ? '移除本人后将失去本部门管理权限，并返回聊天。'
      : ''),
)
const password = computed(() => props.action.kind === 'reset-password')
const field = computed(() =>
  password.value ? '新密码' : props.action.kind === 'add-member' ? '完整用户名' : '部门名称',
)
const editable = computed(() =>
  ['create-department', 'rename-department', 'add-member', 'reset-password'].includes(
    props.action.kind,
  ),
)
const target = computed(() =>
  'user' in props.action
    ? props.action.user.username
    : 'member' in props.action
      ? `${props.action.member.username} · ${props.action.department.name}`
      : 'department' in props.action
        ? props.action.department.name
        : '',
)
const danger = computed(() =>
  [
    'delete-department',
    'remove-member',
    'disable-user',
    'reset-password',
    'revoke-super-admin',
    'revoke-department-admin',
  ].includes(props.action.kind),
)
const validation = computed(() => {
  if (!editable.value) return ''
  if (password.value)
    return [...input.value].length < 8 || [...input.value].length > 128
      ? '密码长度须为 8～128 个字符，首尾空格会保留。'
      : ''
  if (props.action.kind === 'add-member')
    return /^[a-z0-9_]{3,32}$/i.test(input.value.trim())
      ? ''
      : '请输入 3～32 位字母、数字或下划线组成的完整用户名。'
  return !input.value.trim() || [...input.value.trim()].length > 100
    ? '部门名称须为 1～100 个字符。'
    : ''
})

/** 提交一次明确操作，失败保留目标与输入；冲突通知目录同步但不自动重试写入。 */
async function save(): Promise<void> {
  if (busy.value) return
  if (!canPerformAction(auth.user, props.action)) {
    error.value = '当前权限已变化，无法继续此操作。请关闭表单后查看最新目录。'
    return
  }
  attempted.value = true
  if (validation.value) return
  busy.value = true
  error.value = ''
  try {
    await execute(props.action, input.value, controller.signal)
    if (controller.signal.aborted) return
    input.value = ''
    emit('saved')
  } catch (failure) {
    if (controller.signal.aborted) return
    // 密码请求结束即清空；重试时由操作者重新输入，不在失败状态长期保留。
    if (password.value) input.value = ''
    error.value = failure instanceof ApiError ? failure.message : '操作未完成，请稍后重试'
    if (failure instanceof ApiError && [404, 409].includes(failure.status)) emit('conflict')
  } finally {
    busy.value = false
  }
}

// 离页及退出会释放网络请求和敏感草稿，迟到结果不再通知父组件。
onBeforeUnmount(() => {
  controller.abort()
  input.value = ''
})
</script>

<template>
  <UiModal
    :open="true"
    :title="definition[0]"
    :description="description"
    :busy="busy"
    size="md"
    :initial-focus="editable ? '#management-input' : '[data-confirm-cancel]'"
    @update:open="emit('close')"
  >
    <form id="management-action" class="authorization-form" @submit.prevent="save">
      <p v-if="target" class="action-target">
        <span>操作对象</span><strong>{{ target }}</strong>
      </p>
      <label v-if="editable" for="management-input"
        >{{ field }}
        <UiInput
          id="management-input"
          v-model="input"
          :type="password ? 'password' : 'text'"
          :autocomplete="password ? 'new-password' : 'off'"
          :maxlength="action.kind === 'add-member' ? 32 : undefined"
          :disabled="busy"
          :aria-invalid="!!error || (attempted && !!validation)"
          :aria-describedby="
            error || (attempted && validation) ? 'management-validation' : undefined
          "
          @input="error = ''"
        />
      </label>
      <UiFeedback v-if="error || (attempted && validation)" id="management-validation">
        {{ error || validation }}
      </UiFeedback>
    </form>
    <template #footer
      ><UiDialogActions
        form="management-action"
        confirm-type="submit"
        :confirm-label="definition[2]"
        :busy="busy"
        :danger="danger"
        @cancel="emit('close')"
    /></template>
  </UiModal>
</template>

<style scoped>
.authorization-form {
  display: grid;
  gap: 16px;
}
label {
  display: grid;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}
.action-target {
  display: grid;
  gap: 8px;
  padding: 16px;
  margin: 0;
  background: var(--surface-soft);
  border-left: 3px solid var(--brand);
  overflow-wrap: anywhere;
}
.action-target span {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
