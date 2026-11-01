---
name: release-runbook
description: 按团队流程执行一次发版：核对版本号、生成 CHANGELOG 条目、提交并打标签。当用户说要发版、打版本、release、准备发布时使用。
compatibility: 需要 git 与 bash；版本号同时写在 pyproject.toml 与 CHANGELOG.md
allowed-tools: Bash(git:*)
metadata:
  author: harnex-book
  version: "1.1"
---

# 发版手册

## 步骤

1. 跑 `scripts/check_versions.sh`。退出码非 0 就停下来问用户，不要自己改版本号。
2. 版本一致时，按 `references/changelog-template.md` 生成这一版的条目草稿给用户看。
3. 用户确认后，再提交、打标签、推送——这三步都要先给命令。

## 不要做

- 不要修改 `pyproject.toml` 的版本号来「修好」不一致。版本号是人定的。
- 不要在用户没确认时推送。推送不可撤销。
