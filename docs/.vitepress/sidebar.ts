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
  {
    text: '第 3 章 手写第一个 Agent 循环',
    link: '/ch03/',
    collapsed: false,
    items: [
      { text: '3.1 ReAct 与循环的解剖：五个抽屉', link: '/ch03/03_01_react_loop_anatomy' },
      { text: '3.2 七十行代码，一个完整的 Agent：从内核到 CLI', link: '/ch03/03_02_seventy_lines_agent' },
      { text: '本章小结与验收', link: '/ch03/03_99_summary' },
    ],
  },
  {
    text: '第 4 章 工具系统与 MCP',
    link: '/ch04/',
    collapsed: false,
    items: [
      { text: '4.1 从函数列表到工具注册表：粒度与依赖倒置', link: '/ch04/04_01_tool_registry' },
      { text: '4.2 工具描述工程与错误返回设计', link: '/ch04/04_02_tool_description_and_errors' },
      { text: '4.3 第一批正式工具：读、写、改', link: '/ch04/04_03_first_real_tools' },
      { text: '4.4 MCP 与 A2A：把工具搬进独立进程', link: '/ch04/04_04_mcp_and_a2a' },
      { text: '本章小结与验收', link: '/ch04/04_99_summary' },
    ],
  },
  {
    text: '第 5 章 Agent Skills：把方法论装进 Agent',
    link: '/ch05/',
    collapsed: false,
    items: [
      { text: '5.1 两层能力模型：工具管动作，技能包装方法', link: '/ch05/05_01_two_layer_capability_model' },
      { text: '5.2 SKILL.md：十分钟掌握格式', link: '/ch05/05_02_skill_md_format' },
      { text: '5.3 渐进式披露：为什么装 50 个技能包也不怕', link: '/ch05/05_03_progressive_disclosure' },
      { text: '5.4 给 Harnex 装上技能包加载器', link: '/ch05/05_04_skill_loader' },
      { text: '5.5 技能包里的脚本：确定性部分不该即兴发挥', link: '/ch05/05_05_scripts_in_skills' },
      { text: '5.6 决策表：能力该放进哪一层', link: '/ch05/05_06_layer_decision_table' },
      { text: '5.7 技能包的质量与评测', link: '/ch05/05_07_skill_quality_and_eval' },
      { text: '5.8 生态与安全：技能包带知识，不带权力', link: '/ch05/05_08_skill_security' },
      { text: '本章小结与验收', link: '/ch05/05_99_summary' },
    ],
  },
]
