/** 发送前模型确认回归：选择时不询问，实际发送前确认，收到模型输出才开启分界线。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { disposePinia, type Pinia } from 'pinia'
import { computed, nextTick } from 'vue'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { controlledStream } from '@tests/support/vitest/sse'
import { eventFrame, success } from '@tests/support/vitest/chat'
import { response } from '@tests/support/vitest/http'
import { A, B, info } from '@tests/support/data/chat'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { useModelSelectionStore } from '@/features/model-selection/store'
import { useChatStore } from '../../store'
import { lastReplyModel } from '../../model-changes'

const fetchMock = vi.fn<typeof fetch>()
let pinia: Pinia
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  pinia = createTestPinia()
  await authenticate(pinia, fetchMock)
})
// 释放身份定时器和请求，隔离每例的确认状态与浏览器存储。
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

/** 准备已有模型回复的会话，当前选择另一模型，用于验证确认时机与上下文隔离。 */
async function changedConversation() {
  const chat = useChatStore(),
    choices = useModelSelectionStore(),
    data = modelOptionsData()
  choices.options = data
  const previous = {
    model_configuration_id: 'old-model',
    catalog_model_id: 'deepseek:deepseek-flash',
    display_name: 'DeepSeek Flash',
  }
  chat.conversations = [
    {
      id: A,
      title: '已有对话',
      group: '今天',
      persisted: true,
      loaded: true,
      modelSelection: data.default_selection,
      modelSelectionVersion: 3,
      messages: [
        { id: 'previous-user', role: 'user', model: previous, modelReplyStarted: true, blocks: [] },
      ],
    },
  ]
  chat.activeId = A
  await nextTick()
  chat.draft = '尚未发送的消息'
  return { chat, choices, data }
}

it('切换时不询问，发送前才提示；取消后保留草稿且不创建消息', async () => {
  const { chat } = await changedConversation()
  expect(chat.modelChangeConfirmation).toBeNull()
  expect(await chat.send(chat.draft)).toBe(false)
  expect(chat.modelChangeConfirmation?.from.display_name).toBe('DeepSeek Flash')
  expect(chat.modelChangeConfirmation?.to.display_name).toBeTruthy()
  expect(fetchMock).not.toHaveBeenCalled()
  expect(chat.activeConversation?.messages).toHaveLength(1)
  chat.cancelModelChange()
  expect(chat.draft).toBe('尚未发送的消息')
  expect(chat.modelChangeConfirmation).toBeNull()
})

it('确认后只发一次请求，start 不算模型输出，首段正文才显示切换依据', async () => {
  const { chat, data } = await changedConversation(),
    stream = controlledStream()
  fetchMock.mockImplementation(async (url) =>
    url === '/api/chat'
      ? stream.response
      : response({
          conversation: {
            ...info(),
            model_selection: data.default_selection,
            model_selection_version: 3,
            model_selection_issue: null,
          },
        }),
  )
  await chat.send(chat.draft)
  const pending = chat.confirmModelChange()
  expect(chat.draft).toBe('')
  expect(await chat.confirmModelChange()).toBe(false)
  await vi.waitFor(() =>
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/chat')).toHaveLength(1),
  )
  const user = chat.activeConversation!.messages.at(-2)!
  // 与消息列表一样订阅模型输出标记，防止仅修改原始对象却未触发 Vue 更新。
  const repliedModel = computed(() => lastReplyModel(chat.activeConversation!.messages))
  expect(repliedModel.value?.display_name).toBe('DeepSeek Flash')
  expect(user.modelReplyStarted).toBe(false)
  stream.push(
    eventFrame('start', {
      conversation_id: A,
      turn_id: 'current-turn',
      is_new: false,
      model_selection: data.default_selection,
      model_selection_version: 3,
      model: chat.currentModel,
    }),
  )
  await vi.waitFor(() => expect(user.id).toBe('current-turn-user'))
  expect(user.modelReplyStarted).toBe(false)
  stream.push(eventFrame('delta', { conversation_id: A, message_id: 'reply', text: '开始回复' }))
  await vi.waitFor(() => expect(user.modelReplyStarted).toBe(true))
  expect(repliedModel.value?.catalog_model_id).toBe(chat.currentModel!.catalog_model_id)
  stream.push(eventFrame('done', { conversation_id: A, message_id: 'reply', reply: '开始回复' }))
  expect(await pending).toBe(true)
  stream.close()
  fetchMock.mockImplementation(async (url) =>
    url === '/api/chat' ? success(A, '继续回复', false) : response({ conversation: info() }),
  )
  expect(await chat.send('同模型继续')).toBe(true)
  expect(chat.modelChangeConfirmation).toBeNull()
})

it('零输出失败不替换上一实际模型，同原生模型的不同方案不重复询问', async () => {
  const { chat } = await changedConversation()
  chat.activeConversation!.messages.push({
    id: 'failed-user',
    role: 'user',
    model: chat.currentModel,
    modelReplyStarted: false,
    blocks: [],
  })
  await chat.send(chat.draft)
  expect(chat.modelChangeConfirmation?.from.display_name).toBe('DeepSeek Flash')
  chat.cancelModelChange()
  chat.activeConversation!.messages[0]!.model = {
    ...chat.currentModel!,
    model_configuration_id: 'same-native-model-another-config',
  }
  fetchMock.mockImplementation(async (url) =>
    url === '/api/chat' ? success(A, '同模型回复', false) : response({ conversation: info() }),
  )
  expect(await chat.send(chat.draft)).toBe(true)
  expect(chat.modelChangeConfirmation).toBeNull()
})

it('确认期间目标模型改变时重新询问，切换会话会撤销待发送内容', async () => {
  const { chat, choices, data } = await changedConversation()
  await chat.send(chat.draft)
  const another = {
    ...data.providers[0]!.models[0]!,
    model_configuration_id: 'third',
    catalog_model_id: 'deepseek:deepseek-v4-pro',
    display_name: 'DeepSeek V4 Pro',
  }
  choices.options!.providers[0]!.models.push(another)
  chat.activeConversation!.modelSelection = {
    model_configuration_id: 'third',
    reasoning: another.reasoning_control.default,
  }
  expect(await chat.confirmModelChange()).toBe(false)
  expect(chat.modelChangeConfirmation?.to.display_name).toBe('DeepSeek V4 Pro')
  expect(fetchMock).not.toHaveBeenCalled()
  chat.activeId = B
  expect(chat.modelChangeConfirmation).toBeNull()
  expect(await chat.confirmModelChange()).toBe(false)
})
