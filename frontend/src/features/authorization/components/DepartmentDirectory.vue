<!-- 部门与成员双栏工作台：按后端可见范围呈现组织，部门管理员不请求全站账号目录。 -->
<script setup lang="ts">
import UiTag from '@/shared/components/ui/UiTag.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import { computed, ref, watch } from 'vue'
import { Building2, Plus, ArrowRight, Users, Search } from '@lucide/vue'
import { useAuthStore } from '@/features/auth/store'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { decodeDepartment, decodeMember } from '../api'
import { useDirectory } from '../useDirectory'
import type { Department, ManagementAction } from '../types'

const emit = defineEmits<{ action: [action: ManagementAction] }>()
const auth = useAuthStore()
const selected = ref(''),
  searchInput = ref(''),
  search = ref('')
const path = computed(() =>
  auth.can('department:read', auth.user?.department?.id) ? 'departments' : '',
)
const departments = useDirectory(
  path,
  computed(() => ({})),
  decodeDepartment,
)
const department = computed(() => departments.items.value.find((row) => row.id === selected.value))
const memberPath = computed(() =>
  department.value && auth.can('department_member:read', department.value.id)
    ? `departments/${encodeURIComponent(department.value.id)}/members`
    : '',
)
const members = useDirectory(
  memberPath,
  computed(() => ({ search: search.value })),
  decodeMember,
)

/** 选择部门并重置成员筛选，使部门切换与列表归属保持一致。 */
function select(row: Department): void {
  selected.value = row.id
  searchInput.value = ''
  search.value = ''
}

/** 提交成员搜索，保持后续游标与当前筛选一致。 */
function findMembers(): void {
  const value = searchInput.value.trim()
  if (search.value === value) void members.load()
  else search.value = value
}

/** 同步部门与成员快照，保留仍然存在的当前部门。 */
async function reload(): Promise<void> {
  await departments.load()
  await members.load()
}

// 删除当前部门后退回第一个可见部门，不沿用已不存在的资源目标。
watch(departments.items, (rows) => {
  if (departments.loading.value) return
  if (!rows.some((row) => row.id === selected.value)) selected.value = rows[0]?.id ?? ''
})
// 第一页响应写入时仍处于 loading；结束后确定默认选中项。
watch(departments.loading, (loading) => {
  if (!loading && !department.value) selected.value = departments.items.value[0]?.id ?? ''
})
defineExpose({ reload })
</script>

<template>
  <div class="department-workbench">
    <section class="department-index" aria-label="部门目录">
      <div class="section-heading">
        <h2>部门目录</h2>
        <span class="quiet-label">{{
          auth.can('department:create') ? '全站可见' : '我的部门'
        }}</span>
      </div>
      <UiButton
        v-if="auth.can('department:create')"
        class="create-department"
        size="sm"
        @click="emit('action', { kind: 'create-department' })"
        ><Plus :size="15" />新建部门</UiButton
      >
      <p
        v-if="departments.loading.value && !departments.items.value.length"
        role="status"
        class="directory-empty"
      >
        正在展开组织目录…
      </p>
      <UiFeedback v-if="departments.error.value">
        {{ departments.error.value }}
        <template #actions
          ><UiButton size="sm" @click="departments.load()">重试部门目录</UiButton></template
        >
      </UiFeedback>
      <p
        v-else-if="!departments.loading.value && !departments.items.value.length"
        class="directory-empty"
      >
        暂无可见部门
      </p>
      <nav aria-label="选择部门" class="department-options">
        <button
          v-for="row in departments.items.value"
          :key="row.id"
          type="button"
          :aria-current="selected === row.id ? 'true' : undefined"
          @click="select(row)"
        >
          <Building2 :size="18" /><span>{{ row.name }}</span
          ><ArrowRight v-if="selected === row.id" :size="15" />
        </button>
      </nav>
      <UiButton
        v-if="departments.cursor.value"
        size="sm"
        :loading="departments.loading.value"
        @click="departments.load(true)"
        >加载更多部门</UiButton
      >
    </section>
    <section class="member-panel" aria-label="部门成员">
      <template v-if="department">
        <div class="member-heading">
          <div>
            <h2>{{ department.name }}</h2>
          </div>
          <div class="inline-actions">
            <UiButton
              v-if="auth.can('department:update')"
              size="sm"
              @click="emit('action', { kind: 'rename-department', department })"
              >重命名</UiButton
            ><UiButton
              v-if="auth.can('department:delete')"
              size="sm"
              variant="ghost"
              @click="emit('action', { kind: 'delete-department', department })"
              >删除部门</UiButton
            >
          </div>
        </div>
        <div class="directory-toolbar">
          <form
            class="search-form"
            role="search"
            aria-label="搜索部门成员"
            @submit.prevent="findMembers"
          >
            <UiInput
              v-model="searchInput"
              aria-label="搜索成员用户名"
              placeholder="搜索成员用户名"
              type="search"
              size="sm"
              ><template #prefix><Search :size="15" /></template></UiInput
            ><UiButton size="sm" type="submit">搜索</UiButton>
          </form>
          <UiButton
            v-if="auth.can('department_member:add', department.id)"
            variant="primary"
            size="sm"
            @click="emit('action', { kind: 'add-member', department })"
            ><Plus :size="16" />加入成员</UiButton
          >
        </div>
        <p v-if="members.loading.value" role="status">正在加载成员…</p>
        <UiFeedback v-if="members.error.value">
          {{ members.error.value }}
          <template #actions
            ><UiButton size="sm" @click="members.load()">重试成员目录</UiButton></template
          >
        </UiFeedback>
        <div
          v-else-if="!members.loading.value && !members.items.value.length"
          class="directory-empty"
        >
          <Users :size="30" />
          <h3>{{ search ? '没有匹配的成员' : '暂无成员' }}</h3>
          <p>
            {{ search ? '试试其他用户名，或清空搜索。' : '按用户名加入已有账号。' }}
          </p>
        </div>
        <ul class="people-list">
          <li v-for="member in members.items.value" :key="member.id" class="person-row">
            <span class="person-avatar" aria-hidden="true">{{
              member.username.slice(0, 1).toUpperCase()
            }}</span>
            <div class="person-identity">
              <strong
                >{{ member.username
                }}<UiTag size="xs" v-if="member.id === auth.user?.id" tone="brand"
                  >本人</UiTag
                ></strong
              ><span>{{
                member.roles.includes('department_admin') ? '部门管理员' : '部门成员'
              }}</span>
            </div>
            <UiTag size="xs" :tone="member.is_active ? 'brand' : 'neutral'" dot>{{
              member.is_active ? '已启用' : '已停用'
            }}</UiTag>
            <div class="person-actions">
              <UiButton
                v-if="
                  member.roles.includes('department_admin')
                    ? auth.can('role:revoke')
                    : auth.can('role:assign') && member.is_active
                "
                size="sm"
                variant="ghost"
                @click="
                  emit('action', {
                    kind: member.roles.includes('department_admin')
                      ? 'revoke-department-admin'
                      : 'assign-department-admin',
                    department,
                    member,
                  })
                "
                >{{
                  member.roles.includes('department_admin') ? '撤销管理员' : '设为管理员'
                }}</UiButton
              ><UiButton
                v-if="auth.can('department_member:remove', department.id)"
                size="sm"
                variant="ghost"
                @click="emit('action', { kind: 'remove-member', department, member })"
                >移出部门</UiButton
              >
            </div>
          </li>
        </ul>
        <UiButton
          v-if="members.cursor.value"
          :loading="members.loading.value"
          @click="members.load(true)"
          >加载更多成员</UiButton
        >
      </template>
      <div v-else class="directory-empty department-placeholder">
        <Building2 :size="36" />
        <h2>选择部门</h2>
        <p>查看和管理部门成员。</p>
      </div>
    </section>
  </div>
</template>
