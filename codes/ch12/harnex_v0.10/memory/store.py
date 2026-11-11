# harnex/memory/store.py —— 长期记忆：按 key 更新，条目带来源与置信度
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

MEM_PATH = Path("memory.jsonl")


@dataclass
class MemoryItem:
    key: str
    content: str
    kind: str                      # profile / event / procedure
    source: str                    # 哪次会话、显式还是推断
    created_at: float
    confidence: float = 1.0
    expires_at: float | None = None


class MemoryStore:
    def __init__(self):
        self.items: dict[str, MemoryItem] = {}

    def load(self) -> None:
        if not MEM_PATH.exists():
            return
        for line in MEM_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = MemoryItem(**json.loads(line))
                self.items[item.key] = item

    def remember(self, key: str, content: str, kind: str, source: str,
                 confidence: float = 1.0,
                 expires_at: float | None = None) -> None:
        """写入或更新。同一个 key 只留最新一条——用户纠正会覆盖旧记忆。"""
        item = MemoryItem(key=key, content=content, kind=kind,
                          source=source, created_at=time.time(),
                          confidence=confidence, expires_at=expires_at)
        self.items[key] = item
        with MEM_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    def active(self, now: float | None = None) -> list[MemoryItem]:
        now = now or time.time()
        return [it for it in self.items.values()
                if it.expires_at is None or it.expires_at > now]
