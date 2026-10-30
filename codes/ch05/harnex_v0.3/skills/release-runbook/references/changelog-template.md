# CHANGELOG 条目模板

> 项目层为了补齐 `SKILL.md` 里那行引用而写的模板（正文只给了路径）。

```markdown
## [x.y.z] - YYYY-MM-DD

### 新增
- feat(scope): 一句话说清用户能感知到什么变化

### 修复
- fix(scope): 一句话说清原来错在哪、现在对在哪

### 破坏性变更
- 原来怎么用 → 现在怎么用，以及迁移要动什么

### 内部
- refactor / chore / docs 类改动（用户可以跳过这一段）
```

## 写条目的三条规矩

1. **版本号这一行必须与 `pyproject.toml` 的 `version` 完全一致**——`scripts/check_versions.sh` 检查的就是这个。
2. **按「用户能感知到什么」写，不按「改了哪个文件」写。** `fix(parser): 嵌套 YAML 不再解析失败` 比 `修改 parser.py 第 42 行` 有用得多。
3. **条目里的 scope 与提交信息的 scope 保持一致**，这样从 CHANGELOG 能一路查到那次提交。
