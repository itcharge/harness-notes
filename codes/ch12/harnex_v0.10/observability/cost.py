# harnex/observability/cost.py —— 单价放配置：模型换得比代码快
# 只用标准库，不用 pip 装。这段没有任何网络请求。
PRICES = {                                  # 美元 / 百万 token
    "gpt-4o":      {"in": 2.50, "out": 10.00, "cached_in": 1.25},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60,  "cached_in": 0.075},
}


def cost_of(model, tin, tout, cached_in=0):
    """把一次调用折成美元。未知模型不猜价：记 0 并单独告警。"""
    price = PRICES.get(model)
    if price is None:
        return 0.0                          # 表里没有的模型，宁可记 0 也不猜
    fresh = tin - cached_in
    if fresh < 0:
        fresh = 0                           # 缓存数比输入还大，说明数据脏了
    fresh_cost = fresh * price["in"]
    cached_cost = cached_in * price["cached_in"]
    output_cost = tout * price["out"]
    return (fresh_cost + cached_cost + output_cost) / 1e6


# harnex/observability/cost.py（续）—— 哪个技能最贵：把每个 tool 子树下的 llm 成本加起来
def _walk_for_cost(node, owner, totals):
    """沿树往下走。owner 记「当前在谁手下」，进了 tool 就换人。"""
    if node["node"] == "tool":
        owner = node["name"]                      # 进入子树，换主人
    if node["node"] == "llm" and owner:
        tin = node.get("tokens_in") or 0
        tout = node.get("tokens_out") or 0
        cost = cost_of(node["name"], tin, tout)
        totals[owner] = totals.get(owner, 0.0) + cost
    for child in node["children"]:
        _walk_for_cost(child, owner, totals)


def cost_by_tool(trace):
    """技能本身不烧 token，烧的是它引出的后续推理。"""
    totals = {}
    for root in trace["roots"]:
        _walk_for_cost(root, None, totals)
    return totals


# harnex/observability/cost.py（续）—— 月底预测：它是外推，不是承诺
def forecast_month(llm_spans, day_of_month):
    """按当前日均外推 30 天。假设「从今往后和过去一样」——通常不成立。"""
    spent = 0
    for span in llm_spans:
        tin = span.get("tokens_in") or 0
        tout = span.get("tokens_out") or 0
        spent = spent + cost_of(span["name"], tin, tout)
    days = day_of_month
    if days < 1:
        days = 1                        # 1 号才开始跑，除零会炸
    per_day = spent / days
    projected = per_day * 30
    return {"spent": round(spent, 2),
            "per_day": round(per_day, 2),
            "projected": round(projected, 2)}


{"text": "...", "tokens_in": 4200, "tokens_out": 210,
 "cached_in": 3800, "model": "gpt-4o-mini"}
