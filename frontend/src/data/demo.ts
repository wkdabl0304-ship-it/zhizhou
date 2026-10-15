/** 聊天演示内容：提供企业工作场景样例，所有内容均为虚构，不读取真实企业资料。 */
import type { Conversation } from '@/types/chat'

export const suggestions = [
  {
    title: '梳理入职事项',
    description: '让第一天的工作更有条理',
    prompt: '帮我整理一份新员工第一周的入职清单。',
    icon: 'checklist',
  },
  {
    title: '准备项目周报',
    description: '把零散进展变成清晰表达',
    prompt: '帮我拟一份项目周报的结构，包含进展、风险和下周计划。',
    icon: 'report',
  },
  {
    title: '理清一个想法',
    description: '一起找到下一步的方向',
    prompt: '我有一个新的工作想法，请帮我一步步梳理目标和行动计划。',
    icon: 'idea',
  },
]

/** 每次创建独立的样例会话，避免 store 实例和测试之间共享可变消息。 */
export function createDemoConversations(): Conversation[] {
  return [
    {
      id: 'onboarding',
      title: '新员工第一周入职清单',
      group: '今天',
      messages: [
        {
          id: 'onboarding-user',
          role: 'user',
          blocks: [
            { type: 'paragraph', text: '帮我整理一份新员工第一周的入职清单，希望简洁、实用一点。' },
          ],
        },
        {
          id: 'onboarding-assistant',
          role: 'assistant',
          demo: true,
          blocks: [
            {
              type: 'paragraph',
              text: '当然。第一周不必急着熟悉所有事情，可以围绕「安顿下来、了解团队、开始协作」三个目标展开。',
            },
            { type: 'paragraph', text: '第一天 · 把基础准备好' },
            {
              type: 'list',
              items: [
                '确认办公地点、工作时间与入职联系人。',
                '完成账号、邮箱和常用协作工具的开通。',
                '了解团队成员、沟通方式与资料存放位置。',
              ],
            },
            { type: 'paragraph', text: '第二至三天 · 建立工作地图' },
            {
              type: 'list',
              items: [
                '和直属同事对齐岗位职责与近期目标。',
                '阅读与岗位相关的流程和项目背景，记录不清楚的问题。',
                '预约一次简短交流，了解当前项目的进度与协作边界。',
              ],
            },
            { type: 'paragraph', text: '第四至五天 · 从一件小事开始' },
            {
              type: 'list',
              items: [
                '认领一个范围清晰的小任务，走通协作流程。',
                '整理本周收获与疑问，和负责人做一次简短复盘。',
                '约定下周的重点工作与所需支持。',
              ],
            },
            { type: 'paragraph', text: '建议把这份清单作为起点，再根据实际岗位和团队制度调整。' },
          ],
        },
      ],
    },
    {
      id: 'weekly',
      title: '让项目周报更清晰',
      group: '今天',
      messages: [
        {
          id: 'weekly-user',
          role: 'user',
          blocks: [{ type: 'paragraph', text: '项目周报怎么写，才能让同事快速抓住重点？' }],
        },
        {
          id: 'weekly-assistant',
          role: 'assistant',
          demo: true,
          blocks: [
            {
              type: 'paragraph',
              text: '可以把周报控制在一屏内，先给出结论，再补充需要协作的信息。推荐使用下面的结构：',
            },
            {
              type: 'list',
              items: [
                '本周进展：完成了什么，对目标有什么帮助。',
                '风险与阻塞：影响是什么，需要谁在什么时间协助。',
                '下周计划：列出三项以内的重点，并说明预期结果。',
              ],
            },
            {
              type: 'code',
              language: '周报模板',
              text: '本周进展\n- 已完成：\n- 关键结果：\n\n风险与协作\n- 当前问题：\n- 所需支持：\n\n下周计划\n- 重点任务与预期结果：',
            },
            {
              type: 'paragraph',
              text: '把「做了很多事情」换成具体结果，会让周报更容易阅读，也更方便后续跟进。',
            },
          ],
        },
      ],
    },
    {
      id: 'meeting',
      title: '一次高效的项目启动会',
      group: '昨天',
      messages: [
        {
          id: 'meeting-user',
          role: 'user',
          blocks: [{ type: 'paragraph', text: '帮我安排一场 30 分钟的项目启动会。' }],
        },
        {
          id: 'meeting-assistant',
          role: 'assistant',
          demo: true,
          blocks: [
            {
              type: 'paragraph',
              text: '这场会议的目标可以很明确：让大家带着相同的目标和清晰的下一步离开。',
            },
            {
              type: 'list',
              items: [
                '前 5 分钟：介绍项目背景和期望结果。',
                '接下来 10 分钟：明确范围、里程碑和各自职责。',
                '接下来 10 分钟：讨论主要风险与协作方式。',
                '最后 5 分钟：确认负责人、行动项和下次同步时间。',
              ],
            },
            { type: 'paragraph', text: '会前发出一页背景资料，会后只记录结论、负责人和截止时间。' },
          ],
        },
      ],
    },
  ]
}
