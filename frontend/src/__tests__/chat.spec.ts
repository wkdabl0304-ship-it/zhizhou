/** 聊天 store 回归：验证懒建会话、固定演示回复、隔离和刷新语义，无后端或模型依赖。 */
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/chat'

// 每个测试使用独立 Pinia，演示数据工厂防止消息修改污染后续测试。
beforeEach(() => {
  setActivePinia(createPinia())
})

describe('演示聊天状态', () => {
  // 空白不应创建会话，也不应追加固定回复。
  it('空白发送不改变首页与会话列表', () => {
    const chat = useChatStore()
    expect(chat.send(' \n\t ')).toBe(false)
    expect(chat.activeId).toBeNull()
    expect(chat.conversations).toHaveLength(3)
  })

  // 首页第一次发送才创建会话，继续发送复用当前会话。
  it('创建会话并追加明确标识的演示回复', () => {
    const chat = useChatStore()
    expect(chat.send('  请帮我整理工作计划  ')).toBe(true)
    const id = chat.activeId
    expect(chat.activeConversation?.title).toBe('请帮我整理工作计划')
    expect(chat.activeConversation?.messages).toHaveLength(2)
    expect(chat.activeConversation?.messages[0]?.blocks).toEqual([
      { type: 'paragraph', text: '请帮我整理工作计划' },
    ])
    expect(chat.activeConversation?.messages[1]?.demo).toBe(true)
    chat.send('继续聊聊')
    expect(chat.activeId).toBe(id)
    expect(chat.activeConversation?.messages).toHaveLength(4)
  })

  // 切换会话时保留各自消息；重新创建 store 等价于页面刷新，恢复初始样例。
  it('会话互相隔离，新的应用实例恢复演示数据', () => {
    const chat = useChatStore()
    chat.select('weekly')
    chat.send('补充一项')
    expect(chat.activeConversation?.messages).toHaveLength(4)
    chat.select('onboarding')
    expect(chat.activeConversation?.messages).toHaveLength(2)
    chat.select('missing')
    expect(chat.activeId).toBe('onboarding')
    chat.startNew()
    expect(chat.activeConversation).toBeUndefined()
    chat.send('新话题')
    expect(chat.activeId).not.toBe('onboarding')
    setActivePinia(createPinia())
    expect(useChatStore().conversations).toHaveLength(3)
    expect(
      useChatStore().conversations.find((item) => item.id === 'weekly')?.messages,
    ).toHaveLength(2)
  })
})
