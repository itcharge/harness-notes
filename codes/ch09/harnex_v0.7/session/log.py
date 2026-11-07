# harnex/session/log.py —— 会话日志：只追加的事件流，落成 JSONL
import json
import time
from pathlib import Path

LOG_DIR = Path("sessions")


class SessionLog:
    """只追加、不修改的事件流。它同时是真相源和恢复点。"""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or time.strftime("%Y%m%d-%H%M%S")
        self.path = LOG_DIR / f"{self.session_id}.jsonl"
        self.path.parent.mkdir(exist_ok=True)
        self._events: list[dict] = []

    def append(self, kind: str, **payload) -> dict:
        """写一条事件：先落磁盘，再回内存。"""
        event = {"seq": len(self._events), "ts": round(time.time(), 3),
                 "kind": kind, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._events.append(event)
        return event

    def events(self) -> list[dict]:
        return list(self._events)

    @classmethod
    def load(cls, session_id: str) -> "SessionLog":
        """从磁盘恢复一个会话：把 JSONL 读回内存。"""
        log = cls(session_id)
        text = log.path.read_text(encoding="utf-8") if log.path.exists() else ""
        log._events = [json.loads(line) for line in text.splitlines() if line.strip()]
        return log


def project(events: list[dict]) -> list[dict]:
    """把事件流投影成「可以发给模型的消息列表」。"""
    messages = []
    for e in events:
        if e["kind"] == "user_message":
            messages.append({"role": "user", "content": e["content"]})
        elif e["kind"] == "assistant_message":
            messages.append(e["message"])
        elif e["kind"] == "tool_result":
            messages.append({"role": "tool",
                             "tool_call_id": e["tool_call_id"],
                             "content": e["content"]})
    return messages
