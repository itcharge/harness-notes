# harnex/memory/recall.py —— 按相关性挑记忆，而不是全量注入
import re
import time

STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on"}


def keywords(text: str) -> set[str]:
    """粗糙分词：英文按词切，中文切成二字组。够用，且不依赖分词库。"""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)
    han = re.findall(r"[\u4e00-\u9fff]+", text)
    bigrams = [h[i:i + 2] for h in han for i in range(len(h) - 1)]
    return {t.lower() for t in words + bigrams if t.lower() not in STOP}


def _by_score(pair: tuple) -> float:
    return pair[0]


def recall(query: str, items: list, k: int = 5) -> list:
    """给每条记忆打分：关键词重合 × 置信度 × 时间衰减，取前 k 条。"""
    q = keywords(query)
    now = time.time()
    scored = []
    for it in items:
        overlap = len(q & keywords(it.content))
        if overlap == 0:
            continue
        age_days = (now - it.created_at) / 86400
        recency = 1.0 / (1 + age_days / 30)          # 越近越高，30 天衰减一半
        score = overlap * it.confidence * recency
        scored.append((score, it))
    scored.sort(key=_by_score, reverse=True)
    return [it for _, it in scored[:k]]


def memory_prompt(items: list) -> str:
    """把挑出的记忆拼成一段注入文本。全空时不占位。"""
    if not items:
        return ""
    lines = ["关于当前用户，你记得这些（不一定都和本次任务有关）："]
    lines += [f"- {it.content}" for it in items]
    return "\n".join(lines)
