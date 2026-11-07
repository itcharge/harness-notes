# harnex/planning/reflect.py —— 自检：拿完成标准比对工具结果，输出结构化结论
import json

PROMPT = """你是执行者，不是评委。只根据下面给出的【工具实际返回】判断这一步是否达成目标。

子任务：{task}
完成标准：{done_when}

【工具实际返回】
{evidence}

只输出 JSON：
{{"ok": true 或 false,
  "why": "一句话说明判断依据",
  "action": "continue" 或 "retry" 或 "replan" 或 "abort"}}

规则：
- 证据里没有的东西，一律视为没做到。
- 不确定就填 ok=false、action=retry，不要猜。"""


def _to_text(prompt: str) -> str:
    """把 prompt 交给模型，只取文本——复用第 3 章的 chat()。"""
    return chat([{"role": "user", "content": prompt}]).content


def reflect(task: str, done_when: str, evidence: str) -> dict:
    """一次模型调用，返回 {"ok","why","action"}；解析失败时保守地判为未通过。"""
    reply = _to_text(PROMPT.format(task=task, done_when=done_when,
                                   evidence=evidence[:4000]))
    try:
        parsed = json.loads(reply)
        if not isinstance(parsed, dict):
            raise ValueError("返回的不是一个对象")
        if parsed.get("action") not in ("continue", "retry", "replan", "abort"):
            raise ValueError("action 非法")
        return {"ok": bool(parsed["ok"]),
                "why": str(parsed.get("why", "")),
                "action": parsed["action"]}
    except (ValueError, KeyError, json.JSONDecodeError):
        return {"ok": False, "why": "自检结果无法解析，按未通过处理", "action": "retry"}


# harnex/planning/reflect.py（续）—— 重试预算：把「再试一次」变成有数的东西
MAX_SAME_METHOD = 2     # 同一方法最多重试 2 次
MAX_SWITCH = 1          # 换方法最多 1 次
MAX_REFLECT = 20        # 整段任务的自检总次数上限


class Budget:
    """记每一次尝试，到点就拦。"""

    def __init__(self):
        self.same_method = {}
        self.switches = 0
        self.reflects = 0

    def allow_retry(self, method: str) -> bool:
        self.same_method[method] = self.same_method.get(method, 0) + 1
        return self.same_method[method] <= MAX_SAME_METHOD

    def allow_switch(self) -> bool:
        self.switches += 1
        return self.switches <= MAX_SWITCH

    def allow_reflect(self) -> bool:
        self.reflects += 1
        return self.reflects <= MAX_REFLECT
