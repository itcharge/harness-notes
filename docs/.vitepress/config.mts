import { defineConfig } from 'vitepress'
import { sidebar } from './sidebar'

// GitHub Actions 上的 Pages 挂在仓库子路径；本地预览用根路径。
const base = process.env.GITHUB_ACTIONS ? '/harness-notes/' : '/'

export default defineConfig({
  lang: 'zh-CN',
  title: 'Harness 笔记',
  description: '从零开始手写一个能上线的 Agent',
  base,
  ignoreDeadLinks: true,
  markdown: {
    math: true
  },
  themeConfig: {
    nav: [
      { text: '目录', link: '/' },
      { text: '代码', link: 'https://github.com/itcharge/harness-notes/tree/main/codes' },
    ],
    search: {
      provider: 'local',
      options: {
        translations: {
          button: {
            buttonText: '搜索',
            buttonAriaLabel: '搜索'
          },
          modal: {
            noResultsText: '没有找到相关结果',
            resetButtonTitle: '清除查询',
            footer: {
              selectText: '选择',
              navigateText: '切换'
            }
          }
        }
      }
    },
    sidebar,

    socialLinks: [
      { icon: 'github', link: 'https://github.com/itcharge/harness-notes' }
    ],

    editLink: {
      pattern: 'https://github.com/itcharge/harness-notes/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页'
    },

    footer: {
      message: '正文采用 <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/deed.zh" target="_blank">CC BY-NC-ND 4.0</a> 许可，代码采用 <a href="https://github.com/itcharge/harness-notes/blob/main/LICENSE-CODE" target="_blank">MIT</a> 许可',
      copyright: 'Copyright © 2026 ITCharge'
    }
  }
})
