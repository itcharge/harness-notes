# harnex/protocol/events.py —— 所有要推给客户端的东西，统一成带 type 的事件
def emit(kind, **payload):
    """拼一条事件。type 和日志里的 kind 同名（展示专用的事件除外）。"""
    return {"type": kind, **payload}


def on_tool_line(name, line):
    """7.2 的 on_line 回调：命令每打印一行，就变成一条事件推出去。"""
    # push 是「把事件送出去」的出口，由客户端那一层提供（11.5 会看到它的用法）
    push(emit("tool_output", tool=name, line=line))

# 跑起来看到：{"type": "tool_output", "tool": "pytest", "line": "1 failed, 3 passed"}
