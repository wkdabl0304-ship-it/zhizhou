<!-- 全站账号目录：按用户名、状态与归属筛选，管理员操作均固定目标并由共享弹窗提交。 -->
<script setup lang="ts">
import UiTag from '@/shared/components/ui/UiTag.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiSelect from '@/shared/components/ui/UiSelect.vue'
import UiCheckbox from '@/shared/components/ui/UiCheckbox.vue'
import { computed, ref, watch } from 'vue'
import { Search, Users } from '@lucide/vue'
import { useAuthStore } from '@/features/auth/store'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { decodeDepartment, decodeUser } from '../api'
import { useDirectory } from '../useDirectory'
import type { ManagementAction, Query } from '../types'

const emit = defineEmits<{ action: [action: ManagementAction] }>()
const auth = useAuthStore()
const search = ref(''),
  active = ref(''),
  departmentId = ref(''),
  unassigned = ref(false),
  query = ref<Query>({})
const directory = useDirectory(
  computed(() => (auth.can('user:read') ? 'users' : '')),
  query,
  decodeUser,
)
const departments = useDirectory(
  computed(() => (auth.can('department:read') ? 'departments' : '')),
  computed(() => ({})),
  decodeDepartment,
)
// 无部门与具体部门互斥，避免发送服务端明确拒绝的组合筛选。
watch(unassigned, (value) => {
  if (value) departmentId.value = ''
})

/** 将完整筛选作为一个快照提交；重新搜索从第一页开始。 */
function apply(): void {
  query.value = {
    search: search.value.trim(),
    is_active: active.value || undefined,
    unassigned: unassigned.value || undefined,
    department_id: !unassigned.value ? departmentId.value || undefined : undefined,
  }
}

/** 刷新当前筛选的第一页面，供操作成功与冲突同步使用。 */
async function reload(): Promise<void> {
  await directory.load()
}
defineExpose({ reload })
</script>

<template>
  <section class="account-directory" aria-label="全站账号">
    <div class="section-heading">
      <div>
        <h2>全站账号</h2>
        <p class="quiet-label">管理登录状态、部门归属与角色；个人会话始终归账号本人。</p>
      </div>
    </div>
    <form
      class="directory-toolbar account-filters"
      role="search"
      aria-label="筛选账号"
      @submit.prevent="apply"
    >
      <div class="search-form">
        <UiInput
          v-model="search"
          aria-label="搜索账号用户名"
          type="search"
          placeholder="搜索用户名"
          size="sm"
          ><template #prefix><Search :size="15" /></template
        ></UiInput>
      </div>
      <label
        >账号状态<UiSelect
          v-model="active"
          aria-label="账号状态"
          size="sm"
          :options="[
            { value: '', label: '全部状态' },
            { value: 'true', label: '已启用' },
            { value: 'false', label: '已停用' },
          ]" /></label
      ><label
        >所属部门<UiSelect
          v-model="departmentId"
          aria-label="所属部门"
          :disabled="unassigned || departments.loading.value"
          size="sm"
          :options="[
            { value: '', label: '全部部门' },
            ...departments.items.value.map((department) => ({
              value: department.id,
              label: department.name,
            })),
          ]"
      /></label>
      <UiCheckbox v-model="unassigned" class="checkbox-filter">仅无部门</UiCheckbox
      ><UiButton size="sm" type="submit">筛选</UiButton>
    </form>
    <UiFeedback v-if="departments.error.value">
      部门筛选暂不可用。<template #actions
        ><UiButton size="sm" @click="departments.load()">重试部门筛选</UiButton></template
      >
    </UiFeedback>
    <UiButton
      v-if="departments.cursor.value"
      size="sm"
      :loading="departments.loading.value"
      @click="departments.load(true)"
      >加载更多筛选部门</UiButton
    >
    <p v-if="directory.loading.value" role="status">正在加载账号…</p>
    <UiFeedback v-if="directory.error.value">
      {{ directory.error.value }}
      <template #actions
        ><UiButton size="sm" @click="directory.load()">重试账号目录</UiButton></template
      >
    </UiFeedback>
    <div
      v-else-if="!directory.loading.value && !directory.items.value.length"
      class="directory-empty"
    >
      <Users :size="32" />
      <h3>没有匹配的账号</h3>
      <p>调整用户名、状态或部门筛选后重试。</p>
    </div>
    <ul class="people-list">
      <li v-for="user in directory.items.value" :key="user.id" class="person-row account-row">
        <span class="person-avatar" aria-hidden="true">{{
          user.username.slice(0, 1).toUpperCase()
        }}</span>
        <div class="person-identity">
          <strong
            >{{ user.username
            }}<UiTag size="xs" v-if="user.id === auth.user?.id" tone="brand">本人</UiTag></strong
          ><span>{{ user.department?.name ?? '未分配部门' }}</span
          ><UiTag size="xs" v-if="user.roles.includes('super_admin')" tone="accent"
            >超级管理员</UiTag
          ><UiTag size="xs" v-else-if="user.roles.includes('department_admin')">部门管理员</UiTag
          ><UiTag size="xs" v-else>普通用户</UiTag>
        </div>
        <UiTag size="xs" :tone="user.is_active ? 'brand' : 'neutral'" dot>{{
          user.is_active ? '已启用' : '已停用'
        }}</UiTag>
        <div class="person-actions">
          <UiButton
            v-if="auth.can('user:set_active')"
            size="sm"
            variant="ghost"
            @click="emit('action', { kind: user.is_active ? 'disable-user' : 'enable-user', user })"
            >{{ user.is_active ? '停用' : '启用' }}</UiButton
          ><UiButton
            v-if="auth.can('user:reset_password')"
            size="sm"
            variant="ghost"
            @click="emit('action', { kind: 'reset-password', user })"
            >重置密码</UiButton
          ><UiButton
            v-if="
              user.roles.includes('super_admin')
                ? auth.can('role:revoke')
                : auth.can('role:assign') && user.is_active
            "
            size="sm"
            variant="ghost"
            @click="
              emit('action', {
                kind: user.roles.includes('super_admin')
                  ? 'revoke-super-admin'
                  : 'assign-super-admin',
                user,
              })
            "
            >{{ user.roles.includes('super_admin') ? '撤销超管' : '授予超管' }}</UiButton
          >
        </div>
      </li>
    </ul>
    <UiButton
      v-if="directory.cursor.value"
      :loading="directory.loading.value"
      @click="directory.load(true)"
      >加载更多账号</UiButton
    >
  </section>
</template>
