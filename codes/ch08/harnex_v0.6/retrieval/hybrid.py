# harnex/retrieval/hybrid.py —— 关键词与向量各召回一份，按名次融合
def rrf(rank_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """rank_lists 里每个元素是一路检索的有序结果，元素需含 text 字段。"""
    scores: dict[str, float] = {}
    seen: dict[str, dict] = {}
    for lst in rank_lists:
        for rank, item in enumerate(lst):
            key = item["text"]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            seen[key] = item
    pairs = [(score, text) for text, score in scores.items()]
    pairs.sort(reverse=True)
    return [seen[text] for _, text in pairs]
