# harnex/llm/routing.py —— 三档 tier 映射到模型 id：模型名只出现在配置里
# 只用标准库，不用 pip 装。
TIERS = {"small": "gpt-4o-mini", "mid": "gpt-4o", "frontier": "gpt-4o"}


def pick_tier(step):
    """决定这一步用哪一档。从便宜往贵排，先匹配先返回。"""
    kind = step["kind"]
    if kind in ("classify", "extract", "format"):
        return "small"                       # 结构化的小活，小模型够用
    if step["input_tokens"] > 20000:         # 两万 token 以上算长输入
        return "small"                       # 长文档摘要：长不等于难
    if step["needs_multi_step"]:
        return "frontier"
    return "mid"
