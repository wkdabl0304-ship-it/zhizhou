<!-- 认证表单：管理输入、密码显隐和字段校验，向页面提交短生命周期凭据，不自行请求后端。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import { computed, ref } from 'vue'
import { ArrowRight, Eye, EyeOff } from '@lucide/vue'
import type { AuthMode, Credentials } from './types'
import { validateAuth } from './validation'

const props = withDefaults(
  defineProps<{
    mode: AuthMode
    initialUsername?: string
    busy?: boolean
    error?: string
    usernameError?: string
  }>(),
  { initialUsername: '', error: '', usernameError: '' },
)
const emit = defineEmits<{ submit: [credentials: Credentials] }>()
const username = ref(props.initialUsername)
const password = ref('')
const confirmation = ref('')
const visible = ref(false)
const errors = ref({ username: '', password: '', confirmation: '' })
const registering = computed(() => props.mode === 'register')
const idPrefix = computed(() => `auth-${props.mode}`)
const usernameMessage = computed(() => errors.value.username || props.usernameError)

/** 校验输入后向父页面提交；用户名标准化，密码原样保留，等待请求时阻止重复提交。 */
function submit(): void {
  if (props.busy) return
  errors.value = validateAuth(props.mode, username.value, password.value, confirmation.value)
  if (Object.values(errors.value).some(Boolean)) return
  emit('submit', { username: username.value.trim().toLowerCase(), password: password.value })
}
</script>

<template>
  <form
    class="auth-form"
    :aria-label="registering ? '注册账号' : '登录账号'"
    :aria-busy="busy"
    novalidate
    @submit.prevent="submit"
  >
    <UiFeedback v-if="error">{{ error }}</UiFeedback>
    <div class="auth-field">
      <label :for="`${idPrefix}-username`">用户名</label>
      <UiInput
        :id="`${idPrefix}-username`"
        v-model="username"
        name="username"
        autocomplete="username"
        autocapitalize="none"
        :spellcheck="false"
        maxlength="32"
        :placeholder="registering ? '例如 lin_zhou' : '输入你的用户名'"
        :disabled="busy"
        :aria-invalid="Boolean(usernameMessage)"
        :aria-describedby="
          [
            registering && `${idPrefix}-username-hint`,
            usernameMessage && `${idPrefix}-username-error`,
          ]
            .filter(Boolean)
            .join(' ') || undefined
        "
        required
      />
      <p v-if="registering" :id="`${idPrefix}-username-hint`" class="field-hint">
        3–32 位字母、数字或下划线，不区分大小写
      </p>
      <UiFeedback v-if="usernameMessage" :id="`${idPrefix}-username-error`" compact>
        {{ usernameMessage }}
      </UiFeedback>
    </div>
    <div class="auth-field">
      <label :for="`${idPrefix}-password`">密码</label>
      <div class="password-field">
        <!-- HTML 长度以 UTF-16 计；容纳 128 个双码元字符后再按后端字符规则校验。 -->
        <UiInput
          :id="`${idPrefix}-password`"
          v-model="password"
          name="password"
          :type="visible ? 'text' : 'password'"
          :autocomplete="registering ? 'new-password' : 'current-password'"
          maxlength="256"
          :placeholder="registering ? '设置一个密码' : '输入密码'"
          :disabled="busy"
          :aria-invalid="Boolean(errors.password)"
          :aria-describedby="
            [
              registering && `${idPrefix}-password-hint`,
              errors.password && `${idPrefix}-password-error`,
            ]
              .filter(Boolean)
              .join(' ') || undefined
          "
          required
          ><template #suffix
            ><UiIconButton
              class="password-toggle"
              :label="visible ? '隐藏密码' : '显示密码'"
              :aria-pressed="visible"
              :disabled="busy"
              @click="visible = !visible"
            >
              <EyeOff v-if="visible" :size="18" /><Eye v-else :size="18" /></UiIconButton></template
        ></UiInput>
      </div>
      <p v-if="registering" :id="`${idPrefix}-password-hint`" class="field-hint">8–128 个字符</p>
      <UiFeedback v-if="errors.password" :id="`${idPrefix}-password-error`" compact>
        {{ errors.password }}
      </UiFeedback>
    </div>
    <div v-if="registering" class="auth-field">
      <label :for="`${idPrefix}-confirmation`">确认密码</label>
      <UiInput
        :id="`${idPrefix}-confirmation`"
        v-model="confirmation"
        name="confirmation"
        type="password"
        autocomplete="new-password"
        maxlength="256"
        placeholder="再次输入密码"
        :disabled="busy"
        :aria-invalid="Boolean(errors.confirmation)"
        :aria-describedby="errors.confirmation ? `${idPrefix}-confirmation-error` : undefined"
        required
      />
      <UiFeedback v-if="errors.confirmation" :id="`${idPrefix}-confirmation-error`" compact>
        {{ errors.confirmation }}
      </UiFeedback>
    </div>
    <UiButton class="auth-submit" variant="primary" type="submit" :loading="busy">
      <span>{{
        busy ? (registering ? '正在创建账号…' : '正在登录…') : registering ? '创建账号' : '登录知舟'
      }}</span
      ><ArrowRight v-if="!busy" :size="17" />
    </UiButton>
  </form>
</template>

<style scoped>
.auth-field {
  margin-bottom: 20px;
}
label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
}
.password-toggle {
  position: static;
}
.password-toggle:hover {
  color: var(--brand);
}
.field-hint {
  margin: 7px 0 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--text-muted);
}
.auth-field .ui-feedback {
  margin-top: 7px;
}
.auth-form > .ui-feedback {
  margin-bottom: 22px;
}
.auth-submit {
  width: 100%;
  min-height: 46px;
  margin-top: 29px;
}
</style>
