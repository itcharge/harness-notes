# harnex/context/budget.py —— 上下文预算表：一段一段量出谁在吃 token
def rough_tokens(text: str) -> int:
    """粗略估 token：中日韩字符约 1 字 1 token，其余约 4 字符 1 token。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk + (len(text) - cjk) // 4


def budget_report(system: str, tools_json: str, memory: str,
                  messages: str, limit: int = 128_000) -> str:
    rows = [("系统与技能清单", rough_tokens(system)),
            ("工具清单", rough_tokens(tools_json)),
            ("记忆注入", rough_tokens(memory)),
            ("轨迹投影", rough_tokens(messages))]
    total = sum(n for _, n in rows)
    lines = [f"{'区块':<16}{'token':>8}{'占比':>8}"]
    for name, n in rows:
        lines.append(f"{name:<16}{n:>8}{n / limit:>7.1%}")
    lines.append(f"{'合计':<16}{total:>8}{total / limit:>7.1%}")
    if total > limit * 0.7:
        lines.append(f"⚠️ 已超过 {limit * 0.7:.0f} token 警戒线，该压缩了")
    return "\n".join(lines)
