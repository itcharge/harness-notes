# harnex/session/replay.py —— 把一条 JSONL 会话还原成人能读的轨迹
import json
import sys
import time
from pathlib import Path

LOG_DIR = Path("sessions")


def render(session_id: str) -> str:
    path = LOG_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return f"没有找到会话 {session_id}"
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        e = json.loads(raw)
        when = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
        kind = e["kind"]
        if kind == "user_message":
            lines.append(f"[{when}] 用户：{e['content']}")
        elif kind == "assistant_message":
            text = (e["message"].get("content") or "").strip()
            if text:
                lines.append(f"[{when}] Harnex：{text}")
            for call in e["message"].get("tool_calls") or []:
                fn = call["function"]
                lines.append(f"[{when}]   → 调用 {fn['name']} {fn['arguments']}")
        elif kind == "tool_result":
            head = e["content"].strip().replace("\n", " ")[:60]
            lines.append(f"[{when}]   ← {e['name']} 返回：{head}…")
        elif kind == "compaction":
            lines.append(f"[{when}]   ◆ 发生了一次压缩")
    return "\n".join(lines)


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "latest"
    if sid == "latest":
        files = sorted(LOG_DIR.glob("*.jsonl"))
        sid = files[-1].stem if files else ""
    print(render(sid))


# harnex/session/replay.py 追加 —— 列出所有会话的一行摘要
def overview() -> str:
    rows = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        text = path.read_text(encoding="utf-8")
        events = [json.loads(line) for line in text.splitlines() if line.strip()]
        kinds = [e["kind"] for e in events]
        tools = kinds.count("tool_result")
        rows.append(f"{path.stem}  事件 {len(events):3d}  工具调用 {tools:2d}  "
                    f"压缩 {kinds.count('compaction')} 次")
    return "\n".join(rows) or "还没有任何会话记录"
