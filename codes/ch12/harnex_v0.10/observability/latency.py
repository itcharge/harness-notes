# harnex/observability/latency.py —— 把一次 trace 摊成耗时预算表
# 只用标准库，不用 pip 装。
def _accumulate(node, totals):
    """沿树累加每一类节点的耗时。"""
    name = node["node"]
    duration = node["duration_ms"] or 0
    totals[name] = totals.get(name, 0) + duration
    for child in node["children"]:
        _accumulate(child, totals)


def _percent(row):
    return row[1]


def budget_table(trace):
    """返回 [阶段, 占总耗时百分比]，从大到小。"""
    totals = {}
    for root in trace["roots"]:
        _accumulate(root, totals)
    total = sum(totals.values())
    if total == 0:
        total = 1                        # 全是 0 时别除零
    rows = []
    for name, duration in totals.items():
        percent = round(duration * 100 / total)
        rows.append([name, percent])
    rows.sort(key=_percent, reverse=True)
    return rows
