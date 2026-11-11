# harnex/observability/diagnose.py —— 用规则给一次失败归因：把「感觉」换成「哪一类」
# 只用标准库，不用 pip 装。
def classify_failure(trace):
    """返回五类之一。规则是启发式的（按现象猜），但一个错的分类也好过没有分类。"""
    denied = False
    tool_error = False
    lost_context = False
    truncated = False
    for node in trace["index"].values():
        status = node["status"]
        if status == "denied":
            denied = True                        # 有人挡了一下
        if node["node"] == "tool" and status == "error":
            tool_error = True                    # 工具自己报的错
        if node["node"] == "compact" and node.get("lost_used_info"):
            lost_context = True                  # 压缩吃掉了还要用的东西
        if node["node"] == "tool" and node.get("truncated"):
            truncated = True                     # 检索被截断或空手而归
    # 顺序就是优先级：一次失败同时像两类时，先报靠前的那一类
    if denied:
        return "permission"
    if tool_error:
        return "tool_error"
    if lost_context:
        return "context_lost"
    if truncated:
        return "retrieval"
    return "reasoning"                           # 其余：工具都对，判断错了
