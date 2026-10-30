#!/usr/bin/env bash
# skills/release-runbook/scripts/check_versions.sh —— 版本号一致性检查
set -euo pipefail

version=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2 || true)
changelog=$(grep -m1 '^## \[' CHANGELOG.md | sed 's/.*\[\(.*\)\].*/\1/' || true)

if [ -z "$version" ] || [ -z "$changelog" ]; then
  echo "没找到版本号：请确认 pyproject.toml 有 version 字段、CHANGELOG.md 有 '## [x.y.z]' 一行。"
  exit 2
fi

if [ "$version" != "$changelog" ]; then
  echo "版本不一致：pyproject.toml = $version，CHANGELOG.md = $changelog"
  echo "下一步：先改 CHANGELOG.md 的版本号，再重新运行本脚本。"
  exit 1
fi
echo "版本一致：$version"
