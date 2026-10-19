import type { DefaultTheme } from 'vitepress'

export const sidebar: DefaultTheme.Sidebar = [
  {
    text: '第 1 章 什么是 Agent：从会回答到会办事',
    link: '/ch01/',
    collapsed: false,
    items: [
      { text: '1.1 三类常见方案与 Agent 的边界', link: '/ch01/01_01_agent_boundary' },
      { text: '1.2 Harness：模型之外的运行系统', link: '/ch01/01_02_what_is_harness' },
      { text: '1.3 什么时候该用 Agent', link: '/ch01/01_03_when_to_use_agent' },
      { text: '1.4 Harnex 与全书路线', link: '/ch01/01_04_harnex_roadmap' },
      { text: '本章小结与验收', link: '/ch01/01_99_summary' },
    ],
  },
  {
    text: '第 2 章 Prompt 与 LLM：你只需要知道这么多',
    link: '/ch02/',
    collapsed: false,
    items: [
      { text: '2.1 模型是什么：一个无状态函数，外加 token、参数与上下文窗口', link: '/ch02/02_01_what_is_a_model' },
      { text: '2.2 怎么把话说清楚：五零件、一叠消息与四个常见错误', link: '/ch02/02_02_prompt_structure' },
      { text: '2.3 从对话到交付：tool use、结构化输出与模型选型', link: '/ch02/02_03_tool_use_and_model_choice' },
      { text: '本章小结与验收', link: '/ch02/02_99_summary' },
    ],
  },
]
