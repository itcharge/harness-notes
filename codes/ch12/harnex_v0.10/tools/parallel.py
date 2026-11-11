# harnex/tools/parallel.py —— 同一轮里的多个工具调用：能并行就并行
# 只用标准库；registry 和 log 都从前面的章节来（工具注册表、会话日志）。
import asyncio


async def run_calls(calls, registry, log):
    """把一轮里的多个调用发出去：互不依赖的同时跑，各自记各自的日志。"""
    # 这一批共用一个并发标记，事后靠它把交错的事件还原成两条腿
    group = "p" + str(next_seq(log))

    async def run_one(call):
        """一条腿：开工记一笔，收工记一笔。"""
        log.append("tool_start",
                   tool_call_id=call["id"],
                   name=call["name"],
                   group=group)
        result = await registry.call(call["name"], call["args"])
        log.append("tool_result",
                   tool_call_id=call["id"],
                   name=call["name"],
                   group=group,
                   content=result)
        return result

    tasks = []
    for call in calls:
        tasks.append(run_one(call))

    results = await asyncio.gather(*tasks)
    return list(results)

# 跑起来看到：两个调用总耗时约等于「最慢的那一个」，不是两个相加。
# 日志里两条 tool_start 挨着出现，两条 tool_result 的先后可能反过来。
