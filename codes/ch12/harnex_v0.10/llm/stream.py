# harnex/llm/stream.py —— TTFT 计时：从「首个可见 token」算起，不是从首字节
# 只用标准库，不需要 API key：喂它一串现成的块就能跑。
import time


def measure_stream(stream):
    """收完一个流式响应，返回文本和两个延迟指标。"""
    started = time.monotonic()      # 起点只取一次，TTFT 和 E2E 都从它算起
    ttft = None
    parts = []

    for chunk in stream:
        # extract_delta 是正文下面讲的那个小函数：把一块 chunk 翻成看得见的文字
        delta = extract_delta(chunk)
        if not delta:
            continue                # 心跳包、usage 块：屏幕上还什么都没有

        if ttft is None:
            # 只在第一段可见文字到达时记一次，后面的块不再覆盖
            ttft = time.monotonic() - started

        parts.append(delta)

    return {
        "text": "".join(parts),
        "ttft": round(ttft or 0.0, 3),
        "e2e": round(time.monotonic() - started, 3),
    }

# 跑起来看到：{"text": "我先看一下这个文件", "ttft": 0.4, "e2e": 1.3}
# 三个数里只有 ttft 会因为「早一点开始出字」而变小；e2e 基本不动甚至略涨。


# harnex/llm/stream.py（续）—— 把一次流式响应拆成文本与工具调用两路
# 只用标准库；不需要联网，喂一串事先攒好的块就能跑。
import json


def consume_stream(stream):
    """收完一次流式响应：文字边收边拼，工具参数攒齐了再解析。"""
    text_parts = []
    calls = {}          # 按 index 攒：{0: {"name": "fs_read", "args_buf": "..."}}

    for chunk in stream:
        # extract_deltas 是它的「一次可能几段」版本：统一成列表，调用方不用分支
        for delta in extract_deltas(chunk):
            content = delta.get("content")
            if content:
                text_parts.append(content)      # 文字可以来一段拼一段

            for tool_call in delta.get("tool_calls", []):
                index = tool_call["index"]
                if index not in calls:
                    calls[index] = {"name": "", "args_buf": ""}
                slot = calls[index]             # 同一个 index 就是同一次调用

                func = tool_call.get("function", {})
                if func.get("name"):
                    slot["name"] = func["name"]
                slot["args_buf"] += func.get("arguments", "")

    # 循环走完，参数才算齐。边收边解析会拿到 `{"pa` 这种半截 JSON
    parsed = []
    for index in sorted(calls):
        slot = calls[index]
        try:
            args = json.loads(slot["args_buf"])
        except json.JSONDecodeError as exc:
            # 参数不是合法 JSON：留一条带错误的记录，不要整轮丢异常
            parsed.append({"name": slot["name"], "args": None, "error": str(exc)})
            continue
        parsed.append({"name": slot["name"], "args": args, "error": None})

    return {"text": "".join(text_parts), "calls": parsed}

# 跑起来看到：{"text": "", "calls": [{"name": "fs_read", "args": {"path": "src/a.py"}, "error": None}]}
# 参数是一点一点到的，所以 args 只能是攒完之后的结果。
