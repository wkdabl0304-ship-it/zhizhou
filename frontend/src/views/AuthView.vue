<!-- 登录与注册页面：组合共享外壳和表单，协调请求、错误说明及路由跳转。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import { onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthLayout from '@/features/auth/AuthLayout.vue'
import AuthForm from '@/features/auth/AuthForm.vue'
import { AuthApiError, register } from '@/features/auth/api'
import { useAuthStore } from '@/features/auth/store'
import { postLoginPath } from '@/features/auth/validation'
import type { AuthMode, Credentials } from '@/features/auth/types'

const props = defineProps<{ mode: AuthMode }>()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const busy = ref(false)
const error = ref('')
const usernameError = ref('')
let controller: AbortController | undefined

/** 将账号凭据交给后端认证，成功后切换页面；注册仅创建普通账号，不自动建立登录。 */
async function submit(credentials: Credentials): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  auth.notice = ''
  auth.restoreError = ''
  usernameError.value = ''
  controller = new AbortController()
  const signal = controller.signal
  try {
    if (props.mode === 'register') {
      const user = await register(credentials, signal)
      if (signal.aborted) return
      auth.prepareLogin(user.username)
      await router.replace({
        name: 'login',
        query: route.query.redirect ? { redirect: postLoginPath(route.query.redirect) } : {},
      })
    } else {
      await auth.login(credentials, signal)
      await router.replace(postLoginPath(route.query.redirect))
    }
  } catch (failure) {
    if (signal.aborted) return
    const message = failure instanceof AuthApiError ? failure.message : '认证请求失败，请稍后重试'
    if (failure instanceof AuthApiError && failure.code === 20001) usernameError.value = message
    else error.value = message
  } finally {
    if (!signal.aborted) busy.value = false
  }
}

/** 重试因网络原因未完成的身份恢复，验证成功后回到原本要访问的页面。 */
async function retryRestore(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await auth.initialize(true)
    if (auth.isAuthenticated) await router.replace(postLoginPath(route.query.redirect))
  } finally {
    busy.value = false
  }
}

// 切换登录/注册路由或离开认证页时取消请求，阻止迟到的响应恢复已放弃的登录。
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <AuthLayout>
    <div class="auth-content">
      <span class="form-eyebrow">YOUR NEXT CHAPTER</span>
      <h2>{{ mode === 'register' ? '开启你的知舟' : '欢迎回来' }}</h2>
      <p class="form-intro">
        {{
          mode === 'register' ? '创建账号，让每一次思考都有归处。' : '登录，继续你的思考与工作。'
        }}
      </p>
      <UiFeedback
        v-if="auth.restoreError"
        :message="auth.restoreError"
        retry-label="重试验证"
        :busy="busy"
        @retry="retryRestore"
      />
      <UiFeedback v-else-if="mode === 'login' && auth.notice" :message="auth.notice" />
      <!-- 路由切换时重建表单，确保密码、显隐和旧错误不会跨登录/注册页面保留。 -->
      <AuthForm
        :key="mode"
        :mode="mode"
        :initial-username="auth.registeredUsername"
        :busy="busy"
        :error="error"
        :username-error="usernameError"
        @submit="submit"
      />
      <p class="auth-switch">
        <span>{{ mode === 'register' ? '已有账号？' : '还没有账号？' }}</span
        ><RouterLink
          class="auth-link"
          :to="{
            name: mode === 'register' ? 'login' : 'register',
            query: route.query.redirect ? { redirect: postLoginPath(route.query.redirect) } : {},
          }"
          >{{ mode === 'register' ? '返回登录' : '创建账号' }}</RouterLink
        >
      </p>
    </div>
  </AuthLayout>
</template>

<style scoped>
.form-eyebrow {
  display: block;
  margin-bottom: 18px;
  color: var(--accent);
  font-size: 10px;
  letter-spacing: 1.7px;
}
h2 {
  margin: 0 0 10px;
  font-family: 'Songti SC', 'STSong', 'SimSun', serif;
  font-size: 31px;
  font-weight: 400;
  letter-spacing: 1px;
}
.form-intro {
  margin: 0 0 30px;
  color: var(--text-secondary);
  font-size: 13px;
}
.auth-switch {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 24px 0 0;
  color: var(--text-muted);
  font-size: 13px;
}
.auth-link {
  border: 0;
  padding: 4px;
  background: transparent;
  color: var(--brand);
  text-decoration: none;
  font: inherit;
}
.auth-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (max-width: 760px) {
  .form-eyebrow {
    display: none;
  }
  h2 {
    font-size: 28px;
  }
}
</style>
