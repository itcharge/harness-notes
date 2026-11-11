# harnex/context/compact.py —— 压缩：先瘦身工具结果，再裁窗口，最后才摘要
def shrink_tool_results(events: list[dict], keep_chars: int = 400) -> list[dict]:
    """工具结果超长时只留开头一段——完整内容仍在日志里。"""
    out = []
    for e in events:
        if e["kind"] == "tool_result" and len(e["content"]) > keep_chars:
            e = {**e, "content": e["content"][:keep_chars] + "\n…（已截断，完整内容见日志）"}
        out.append(e)
    return out


def window(events: list[dict], keep: int = 30) -> list[dict]:
    """滑动窗口：保留最近 keep 条事件。"""
    return events[-keep:]


def _event_text(e: dict) -> str:
    """把一条事件还原成一行文本——助手发言藏在 message 里，要单独取。"""
    if e["kind"] == "assistant_message":
        msg = e["message"]
        parts = [msg.get("content") or ""]
        for call in msg.get("tool_calls") or []:
            fn = call["function"]
            parts.append(f"(调用 {fn['name']} {fn['arguments']})")
        return " ".join(p for p in parts if p)
    return e.get("content", "")


def summarize(old_events: list[dict], chat_fn) -> str:
    """把要丢弃的事件交给模型摘成一段。"""
    text = "\n".join(f"[{e['kind']}] {_event_text(e)}" for e in old_events)
    prompt = ("下面是一段 Agent 与用户的对话记录。请压缩成不超过 150 字的摘要，"
              "保留：任务目标、用户给的约束与纠正、未完成的事项、关键事实"
              "（路径、ID、结论）。丢掉：过程细节、重复内容。\n\n" + text)
    return chat_fn([{"role": "user", "content": prompt}]).content


def compact(events: list[dict], chat_fn, keep_recent: int = 24) -> list[dict]:
    """压缩 = 瘦身 → 摘要老段 → 拼上最近段。返回新投影，不动原日志。"""
    slim = shrink_tool_results(events)
    if len(slim) <= keep_recent:
        return slim
    old, recent = slim[:-keep_recent], window(slim, keep_recent)
    digest = summarize(old, chat_fn)
    return [{"kind": "compaction", "summary": digest}] + recent


def project(events: list[dict]) -> list[dict]:
    """和 6.1 的 project 相比，多认一种事件：压缩摘要。"""
    messages = []
    for e in events:
        if e["kind"] == "compaction":
            messages.append({"role": "system",
                             "content": "以下是对之前对话的摘要：\n" + e["summary"]})
        elif e["kind"] == "user_message":
            messages.append({"role": "user", "content": e["content"]})
        elif e["kind"] == "assistant_message":
            messages.append(e["message"])
        elif e["kind"] == "tool_result":
            messages.append({"role": "tool", "tool_call_id": e["tool_call_id"],
                             "content": e["content"]})
    return messages
