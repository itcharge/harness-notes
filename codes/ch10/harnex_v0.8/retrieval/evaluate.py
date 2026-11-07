# harnex/retrieval/evaluate.py —— 十题对照，手工评分
import asyncio

from retrieval import search_tool
from retrieval.rag_min import embed, top_k

CASES = [
    # 单跳事实题：答案就在一段里
    {"q": "配置里默认的超时是多少秒？", "source": ["config.md"], "must": "30"},
    {"q": "项目使用的测试框架是什么？", "source": ["dev.md"], "must": "pytest"},
    {"q": "日志默认保留几天？", "source": ["ops.md"], "must": "7"},
    # 多跳题：答案分散在多篇文档里，来源写一列
    {"q": "A 模块的维护者是哪个团队？该团队还负责哪些服务？",
     "source": ["team.md", "teams.md", "services.md"], "must": "基础设施"},
    {"q": "处理订单的服务由哪个团队维护？它用的是哪个数据库？",
     "source": ["teams.md", "arch.md"], "must": "Postgres"},
    {"q": "上次故障复盘提的改进项，现在是哪个团队在做？",
     "source": ["incident.md", "teams.md"], "must": "基础设施"},
    # 不该检索的题：答案就在对话里，或根本不需要检索
    {"q": "把上面那句话改成更正式的说法。", "source": None, "must": None},
    {"q": "你好，我们接着刚才那个问题聊。", "source": None, "must": None},
    {"q": "把刚才找到的超时值乘二，写进 config.md。", "source": None, "must": "60"},
    {"q": "谢谢你，先到这里。", "source": None, "must": None},
]


# harnex/retrieval/evaluate.py（续）
def ask(client, prompt: str) -> str:
    """一句话问模型、取回文本。"""
    resp = client.chat.completions.create(
        model="deepseek-flash",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def strategy_naive(client, question: str) -> tuple[str, int]:
    """检索一次就答。返回 (答案, 检索轮数)。"""
    hits = top_k(embed(client, [question])[0], search_tool.INDEX, k=4)
    context = "\n\n".join(h["text"] for h in hits)
    prompt = f"根据下面的资料回答问题。\n\n{context}\n\n问题：{question}"
    return ask(client, prompt), 1


def strategy_agentic(client, question: str) -> tuple[str, int]:
    """交给模型自己决定检索几次。执行逻辑就是第 3 章那个循环，这里一行都没重写。"""
    from build_registry import build_registry
    from loop.agent import run_turn
    from session.log import SessionLog

    search_tool.CLIENT = client          # 8.4.4 留的那个口子，这儿接上
    log = SessionLog()
    answer = asyncio.run(run_turn(question, build_registry(), log))
    rounds = sum(1 for e in log.events()
                 if e["kind"] == "tool_result" and e.get("name") == "search_docs")
    return answer, rounds


def score(answer: str, case: dict) -> dict:
    """最朴素的评分：关键词是否出现 + 期望来源是否都引到。"""
    if not case["must"]:
        return {"answer_ok": True, "cited": None}
    sources = case["source"] or []
    return {
        "answer_ok": case["must"] in answer,
        "cited": all(s in answer for s in sources) if sources else None,
    }
