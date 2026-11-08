# harnex/retrieval/full_context.py —— 最简形态：不检索，整份资料塞进消息
# client 是 OpenAI SDK 的客户端（第 2 章那个）。它的 chat 够用，但没有 embeddings 接口——
# 8.2 要算向量时得换一个带嵌入的客户端，见 embed() 的注释。
def answer(client, question: str, docs: str) -> str:
    system = (
        "只根据下面的资料回答问题。资料里没有提到的，直接说资料中没有，"
        "不要凭常识补充。\n\n"
        f"===== 资料开始 =====\n{docs}\n===== 资料结束 ====="
    )
    resp = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    )
    return resp.choices[0].message.content
