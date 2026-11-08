# harnex/retrieval/rag_min.py —— 最小工作集：切块、嵌入、余弦检索
import json
import math


def chunk(text: str, size: int = 400, overlap: int = 60) -> list[str]:
    """先按空行切段，再把小段合并到接近 size；超长段硬切并保留 overlap。"""
    size = max(1, size)                        # 块大小给 0 会切不动，这里兜住
    overlap = min(max(overlap, 0), size - 1)   # 重叠顶满整块时 p[size-overlap:] 原地不动
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > size:
            chunks.append(p[:size])
            p = p[size - overlap:]
        if len(buf) + len(p) + 2 <= size:
            buf = f"{buf}\n\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def embed(client, texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """把一批文本转成向量。批量送比逐条送快得多。

    DeepSeek 没有 embeddings 接口，这个 client 得另找一家（任何 OpenAI 兼容、
    带 /embeddings 的都行）。建索引和查询用同一个模型，两串数才在同一个空间。
    """
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


def item_score(item: dict) -> float:
    return item["score"]


def top_k(qv: list[float], index: list[dict], k: int = 3) -> list[dict]:
    """暴力算相似度，取前 k。index 里的每条记录都带上自己的 score。"""
    scored = [dict(it, score=cosine(qv, it["vec"])) for it in index]
    scored.sort(key=item_score, reverse=True)
    return scored[:k]


def index_docs(client, docs: dict[str, str]) -> list[dict]:
    """docs: {文件名: 全文} → 一条条带来源的索引记录。"""
    items: list[dict] = []
    for name, text in docs.items():
        for piece in chunk(text):
            items.append({"source": name, "text": piece})
    vecs = embed(client, [it["text"] for it in items])
    for it, v in zip(items, vecs):
        it["vec"] = v
    return items


def save_index(index: list[dict], path: str = "index.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
