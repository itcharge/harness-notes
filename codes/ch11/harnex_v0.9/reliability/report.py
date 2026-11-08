# harnex/reliability/report.py —— 失败记录：一份结构化，一份人读
import time


def classify_kind(attempts):
    """从尝试记录里定出这次失败的类别，喂给 10.6 统计。"""
    # 从后往前找：最后一次尝试最能说明这次为什么没做成。
    for attempt in reversed(attempts or []):
        # 用记录里当时就写下的 kind。那是失败发生那一刻从工具返回里认出来的，不是事后猜的。
        if attempt.get("kind"):
            return str(attempt["kind"])
    # 一条都没有就返回 unknown。它不是「没有失败」，是分类器没认出来。
    return "unknown"


def build_failure(step, expected, actual, attempts, advice, log_path):
    """构造失败记录。它同时是给人看的报告，和 10.6 统计用的样本。"""
    return {
        # 这里用 time.time() 而不用 monotonic：人要读的是「几点几分」，得是墙上时间。
        "ts": round(time.time(), 3),
        "step_id": step["id"],
        "step_task": step["task"],
        "expected": expected,
        "actual": actual,
        "attempts": attempts,             # [{"method":..., "why":..., "kind":...}, ...]
        "advice": advice,
        "kind": classify_kind(attempts),  # 10.1 的失败分类，喂给 10.6
        "log_path": log_path,             # 完整轨迹在哪，给人足够线索
    }


def render_human(failure):
    """把失败记录渲染成一段人读的文本。"""
    lines = []
    for index, attempt in enumerate(failure["attempts"]):
        lines.append(f"  {index + 1}. {attempt['method']} —— {attempt['why']}")
    if lines:
        tried = "\n".join(lines)
    else:
        tried = "  （没有重试记录）"

    return "\n".join([
        f"任务中止，停在第 {failure['step_id']} 项「{failure['step_task']}」。",
        f"期望：{failure['expected']}",
        f"实际：{failure['actual']}",
        f"失败类型：{failure['kind']}",
        f"试过什么：\n{tried}",
        f"建议：{failure['advice']}",
        f"完整轨迹：{failure['log_path']}",
    ])

# 渲染出来的样子（这里把记录手写出来，就不必真跑一遍流水线）：
# 任务中止，停在第 3 项「给客户发确认信」。
# 期望：邮件发出，返回 message-id
# 实际：SMTP 连接超时，重试 2 次都失败
# 失败类型：timeout
# 试过什么：
#   1. 直连 SMTP —— 30 秒超时
#   2. 换备用端口 —— 仍然超时
# 建议：这一项依赖的网络出口需要人工确认；后面的第 4、5 项没动
# 完整轨迹：sessions/2026-11-07.jsonl
