<!-- 组织与权限页面：编排部门、账号目录与操作反馈，领域契约及目录生命周期留在 authorization。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Building2, Users, ShieldCheck } from '@lucide/vue'
import { useAuthStore } from '@/features/auth/store'
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
import DepartmentDirectory from '@/features/authorization/components/DepartmentDirectory.vue'
import UserDirectory from '@/features/authorization/components/UserDirectory.vue'
import ManagementDialog from '@/features/authorization/components/ManagementDialog.vue'
import type { ManagementAction } from '@/features/authorization/types'
import { canPerformAction } from '@/features/authorization/access'
import '@/features/authorization/authorization.css'

const auth = useAuthStore()
const departmentsAllowed = computed(() => auth.can('department:read', auth.user?.department?.id))
const tab = ref<'departments' | 'users'>(departmentsAllowed.value ? 'departments' : 'users')
const action = ref<ManagementAction | null>(null),
  notice = ref('')
const departments = ref<InstanceType<typeof DepartmentDirectory>>(),
  users = ref<InstanceType<typeof UserDirectory>>()

// 降权后仍可能保留部门管理资格；切回可见视图，并关闭不再有权提交的旧目标。
watch(
  () => JSON.stringify([auth.accessToken, auth.user?.grants, auth.user?.department?.id]),
  () => {
    if (tab.value === 'users' && !auth.can('user:read')) tab.value = 'departments'
    if (tab.value === 'departments' && !departmentsAllowed.value && auth.can('user:read'))
      tab.value = 'users'
    if (action.value && !canPerformAction(auth.user, action.value)) {
      action.value = null
      notice.value = auth.notice ? '' : '权限已变化，已关闭无法继续的操作，请查看当前可用目录。'
    }
  },
)

/** 打开固定目标的管理操作，清理此前的权限变化说明。 */
function openAction(value: ManagementAction): void {
  action.value = value
  notice.value = ''
}

/** 切换管理视图并清理上一视图的权限说明。 */
function changeTab(value: 'departments' | 'users'): void {
  tab.value = value
  notice.value = ''
}

/** 同步当前目录，操作目标仍由弹窗原始快照固定，失败写入不会自动重试。 */
async function reload(): Promise<void> {
  await Promise.all([departments.value?.reload(), users.value?.reload()])
}

/** 写入成功后先关闭表单，再同步本人权限和公开目录，撤权及移出本人会自然退出此页。 */
async function saved(): Promise<void> {
  action.value = null
  notice.value = ''
  await auth.refreshIdentity()
  await reload()
}

/** 页面重新可见时重新确认授权及当前目录，保留正在编辑的操作避免无意丢稿。 */
async function synchronize(): Promise<void> {
  if (document.hidden || action.value) return
  await auth.refreshIdentity()
  await reload()
}
onMounted(() => {
  window.addEventListener('focus', synchronize)
  document.addEventListener('visibilitychange', synchronize)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', synchronize)
  document.removeEventListener('visibilitychange', synchronize)
})
</script>

<template>
  <div class="organization-page">
    <UiPageHeader title="组织与权限" class="organization-header" />
    <div class="organization-scroll">
      <section class="organization-intro" aria-label="管理范围">
        <div class="scope-summary">
          <ShieldCheck :size="26" /><span>当前管理范围</span
          ><strong>{{
            auth.can('user:read') ? '全站组织与账号' : auth.user?.department?.name
          }}</strong>
          <p>管理权限不包含他人的个人会话。</p>
        </div>
      </section>
      <nav class="organization-tabs" aria-label="组织管理视图">
        <button
          v-if="departmentsAllowed"
          type="button"
          :aria-current="tab === 'departments' ? 'page' : undefined"
          @click="changeTab('departments')"
        >
          <Building2 :size="17" />部门与成员</button
        ><button
          v-if="auth.can('user:read')"
          type="button"
          :aria-current="tab === 'users' ? 'page' : undefined"
          @click="changeTab('users')"
        >
          <Users :size="17" />全站账号
        </button>
      </nav>
      <UiFeedback v-if="notice" :message="notice" />
      <DepartmentDirectory
        v-if="tab === 'departments' && departmentsAllowed"
        ref="departments"
        @action="openAction"
      />
      <UserDirectory v-else-if="auth.can('user:read')" ref="users" @action="openAction" />
    </div>
    <ManagementDialog
      v-if="action"
      :action="action"
      @close="action = null"
      @saved="saved"
      @conflict="reload"
    />
  </div>
</template>
