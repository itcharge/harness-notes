# harnex/observability/funnel.py —— 任务完成率：把技术成功率和用户放弃率合成一个数
# 只用标准库，不用 pip 装。
def completion_rate(events):
    """按轮次看最终去向：做完了、失败了、还是用户走了。"""
    outcome = {}                        # turn_id → 这一轮最后是什么状态
    for event in events:
        kind = event["kind"]
        if kind == "turn_done":
            status = event.get("status", "done")
            outcome[event["turn_id"]] = status
        elif kind == "cancel":
            outcome[event["turn_id"]] = "cancelled"      # 用户中途走了
    done = 0
    cancelled = 0
    for status in outcome.values():
        if status == "done":
            done += 1
        if status == "cancelled":
            cancelled += 1
    total = len(outcome)
    if total == 0:
        rate = 0.0
    else:
        rate = round(done / total, 3)
    return {"total": total, "done": done, "rate": rate, "cancelled": cancelled}
