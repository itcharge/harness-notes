# harnex/retrieval/search_tool.py —— 把检索做成一个工具
from retrieval.rag_min import embed, top_k

CLIENT = None                            # 由装配代码注入：能算向量的那个 client
INDEX: list[dict] = []                   # 同上：8.2 建好的索引，启动时塞进来


def search_docs(args: dict) -> str:
    """在知识库里检索相关段落。args: {query: str, k?: int}"""
    query = str(args.get("query", "")).strip()
    if not query:
        return "错误：query 不能为空。"
    k = int(args.get("k", 4))
    if CLIENT is None or not INDEX:
        return "知识库还没接上索引，检索不了。先建一次索引，再问我。"
    hits = top_k(embed(CLIENT, [query])[0], INDEX, k=k)
    if not hits:
        return "没有找到相关段落。可以换个关键词再试，或直接用 fs_read 打开原文件。"
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] 来源：{h['source']}（相关度 {h['score']:.2f}）\n{h['text']}")
    return "\n\n".join(blocks)
