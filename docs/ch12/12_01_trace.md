# 12.1 轨迹 trace：给每次决策装行车记录仪

## 12.1.1 三种说不清的情况

上一章你把控制台发给了同事。他用了一会儿，问出第二个问题：**能不能把刚才那次任务的执行过程给我看看？**

你能给他看的只有 **结果**——那张清单、那段回答、或者一条红字报错。**过程**你手上没有。

这不是界面不够好，是 **数据从没被串起来**。第 6 章让程序把每一步写进一个文件，叫会话日志。它就是一本流水账：一行记一件事，一行就叫一条 **事件**（event）。`llm_call` 记一次模型调用。`tool_result` 记一次工具返回。`todo_update` 记一次清单更新。

账记得很全。可它是平铺的：一条接一条往下排，谁属于谁看不出来。这些事件只回答「发生了什么」，没人把它们拼成「它怎么走到这里的」。

于是有三种场景，你都说不出话：

- **它做错了，你不知道错在哪一步。** 是检索没找到（检索就是按关键词去资料里翻），还是找到了、但判断错了？
- **月底账单来了，你猜不出钱花在哪。** 总数你知道，但「哪个任务最贵」答不上来。
- **有人说「感觉变慢了」。** 你打开终端（那个只能打字、只能看字的黑框框），觉得确实慢，然后无从下手。

**这三件事其实是同一件事：你的 harness 是个黑盒。**

harness 是套在模型外面的那层程序。模型只负责说话。真去读文件、跑命令、记账的，是这层程序。盒子是封死的：到没到终点你知道，一路怎么开过来的，你看不见。

第 11 章装了一副仪表盘，那是给用户看的，显示「它现在在做什么」。这一章要装的是**给自己看的行车记录仪**。任务结束之后拆开看：每一秒发生了什么，每一项花了多少油。

## 12.1.2 把一条条记录折成树

先说这份记录长什么样。会话日志是 **一条线**：每写一条，`seq`（序号）加一。一次真实调用长这样：

```jsonl
{"seq": 12, "kind": "span_start", "span_id": "a1b2c3d4e5f6", "parent_id": null, "node": "turn", "name": "整理 TODO"}
{"seq": 13, "kind": "span_start", "span_id": "b2c3d4e5f6a1", "parent_id": "a1b2c3d4e5f6", "node": "llm", "name": "gpt-4o"}
{"seq": 14, "kind": "tool_call", "parent_id": "b2c3d4e5f6a1", "tool": "search_code", "args": {"pattern": "TODO"}}
{"seq": 15, "kind": "span_end", "span_id": "b2c3d4e5f6a1", "duration_ms": 3120, "tokens_in": 4820, "tokens_out": 96, "status": "ok"}
{"seq": 16, "kind": "span_end", "span_id": "a1b2c3d4e5f6", "duration_ms": 32400, "status": "ok"}
```

这五行不用逐字读，看两处就够。

一处是**成对**。`span_start` 说「这段工作开始了」，`span_end` 说「结束了」。一段有头有尾的工作，在这本书里叫 **span**。这一轮任务是一个 span，里面那次模型调用也是一个 span，那次搜索还是一个 span。

另一处是**谁挂在谁下面**。这条线里有个关系，**没有任何一条事件直接说**：「`search_code` 属于这次调用，这次调用属于这一轮」。它藏在两个 `parent_id` 字段里。`parent_id` 记的是上级的编号。人勉强读得出来，程序与界面都不行。

**trace 就是把这条线按 `parent_id` 折成一棵树。** trace 原意是「痕迹」，在这里指一份能按层级回放的执行记录。树就是层级：最外面是这一轮任务，它下面挂着几次模型调用，每次调用下面再挂着工具调用。

## 12.1.3 存下来的和展示的分开

先破一个误会：**trace 不是新开一份存储。**

值得专门说一句，是因为你一旦当它是「另一份数据」，就会长出两个麻烦。两份数据要同步，不同步就互相打脸。存下来的只有一份，展示出来的样子可以有好几份。

第 6 章立过两条不变式——不变式就是从开头到结尾都不许破的规矩。第二条是**状态由日志投影得出**。这条规矩已经兑现过两次。`project()` 把日志投成「这一轮发给模型的消息」（6.1）。`project_todos()` 把它投成待办清单（9.2）。现在交出**第三个投影**：

> **trace 是 `SessionLog` 的第三个投影。**

「投影」是从同一个东西上、换个角度照出来的一份样子。日志里能拼出 trace，是因为**每条 span 事件本来就带了 `parent_id`**。所以你要做的只有一件事：**写事件时带上父节点，再加上你以后想在看板上看到的字段。** 加字段，不是加一个系统。

> **为什么死守这条？** 一旦 trace 变成「独立的一份数据」，就有了两份真相，也就有了「日志和看板对不上」的土壤。只要它是投影，就能**随时删掉重建**：删库、重放日志，一字不差。
>
> 判据一句话：**能随时从日志重建的，是投影；不能的，是新的事实。**

## 12.1.4 树上有哪些节点

不用把每个动作都变成节点。节点就是树上的一格。把每个动作都记上，树会吵得没法看。值得记的只有五类：

| 节点 | 什么时候产生 | 谁关心 |
| --- | --- | --- |
| `turn` | 用户发一句话，任务开始 | 成本看板的顶层口径 |
| `llm` | 每一次模型调用 | token 与延迟的大头 |
| `tool` | 每一次技能执行 | 「哪个技能最贵、最慢」 |
| `approval` | 每一次审批等待 | 人挡了多少时间（11.4） |
| `compact` | 每一次上下文压缩 | 「信息什么时候丢的」（第 6 章） |

前三个是主干。后两个最容易被漏掉，却都有一次「意外好用」的时候（一开始嫌麻烦，后来发现离不开）。`approval` 让「人点头之前挡了多少时间」第一次有了数。`compact` 让「我明明给过它这条信息」变成可核对的事实。12.2 那个 bug 就出在这上面。

每个节点记什么，也就跟着定了：

| 字段 | 作用 |
| --- | --- |
| `span_id` / `parent_id` | 拼树 |
| `node` / `name` | 分类与显示（`node` 是上面五类，`name` 是具体工具名或模型名） |
| `duration_ms` | 延迟归因 |
| `tokens_in` / `tokens_out` | 成本归因 |
| `status` | `ok` / `error` / `denied`，出问题时一眼定位 |

`duration_ms` 的单位是毫秒，一千毫秒是一秒。

**耗时要在现场记，不能事后算。** 事后算需要两个时间点。日志里要是只有「开始」没有「结束」，你就只能拿「下一条事件的时间」去凑。多轮对话和并行执行下，这么凑出来的数全是错的（11.3 吃过一次亏）。所以 span 要成对写：

```python
# harnex/observability/trace.py —— span：一段工作装上开始与结束，耗时当场落盘
# 只用标准库，不用 pip 装。要跑这段，先准备一个 log 对象：
# 它只要能调 append(dict) 就行，普通列表就可以。
import time
import uuid
from contextlib import contextmanager


# @contextmanager 是个装饰器。它让下面这个函数能配 with 用：
# 进 with 时先跑 yield 之前那段，出 with 时再跑 finally 那段。
# 所以函数里出现了 yield —— 这里的 yield 只是「把控制权交回去一会儿」，不产出数据。
@contextmanager
def span(log, node, name, parent_id=None, **fields):
    """用 with 包住一段工作：进出各落一条事件，耗时当场记下。

    多传的关键字参数（**fields）会原样放进记录，留给以后看板用。
    """
    span_id = uuid.uuid4().hex[:12]        # 12 位随机编号，用来互相挂
    record = {"id": span_id, "parent_id": parent_id, "node": node,
              "name": name, "status": "ok"}
    record.update(fields)                  # 想额外记的字段，直接并进来

    start_time = time.monotonic()          # 单调时钟，只拿它算差值
    log.append({"kind": "span_start", "span_id": span_id,
                "parent_id": parent_id, "node": node, "name": name})
    try:
        yield record
    except Exception:
        record["status"] = "error"        # 抛出去的异常也照样记一笔
        raise
    finally:
        # 不管上面成没成，都得补一条结束事件，否则这一段永远悬着
        elapsed = time.monotonic() - start_time
        end_event = {"kind": "span_end", "span_id": span_id,
                     "duration_ms": round(elapsed * 1000)}
        for key in record:
            if key in ("id", "parent_id", "node", "name"):
                continue
            end_event[key] = record[key]
        log.append(end_event)
```

用起来就是这样：

```python
# 这段是用法示例，接着上一段读。call_model / search_code 来自第 4、7 章，
# 单独粘出来跑会报 NameError —— 它演示的是「怎么套 with」，不是完整程序。
with span(log, "turn", user_text) as turn:
    with span(log, "llm", model, parent_id=turn["id"]) as llm:
        reply = call_model(messages)
        llm["tokens_in"] = reply.tokens_in
        llm["tokens_out"] = reply.tokens_out
    args = {"pattern": "TODO"}
    with span(log, "tool", "search_code", parent_id=llm["id"], args=args) as tool:
        hits = search_code(args)
        tool["truncated"] = hits["truncated"]   # 12.2 靠它认检索截断
```

两处容易混，单独说：

- **父子关系记的是「属于谁」，不是「谁先谁后」。** 上面那个 `tool` 挂在请求它的 `llm` 之下。它在时间上却发生在 `llm` 结束之后。
- **`finally` 保证异常路径也写下 `span_end`**，不留悬空节点。`finally` 是 Python 里「不管前面成没成、这段都执行」的写法。`status` 也顺手记好：抛异常是 `error`，审批被拒是 `denied`。11.4 那次拒绝本来就有事件，这里只是把它落进字段。

## 12.1.5 用一个函数拼树

span 成了对，投影落到代码上就是一个循环：函数把事件从头过一遍，边过边往树上挂。

```python
# harnex/observability/trace.py（续）—— project_trace：把平铺的事件折成一棵树
def project_trace(events):
    """从会话日志投影出节点树。日志一个字节没改，只是换个读法。"""
    nodes = {}          # span_id → 节点
    order = []          # 按落盘顺序记住都有哪些 span
    for event in events:
        span_id = event.get("span_id")
        if not span_id:
            continue                      # 没带 span_id 的事不参与拼树
        kind = event["kind"]
        if kind == "span_start":
            node = {"id": span_id, "parent": event.get("parent_id"),
                    "node": event["node"], "name": event["name"],
                    "duration_ms": None, "tokens_in": 0,
                    "tokens_out": 0, "status": "ok", "children": []}
            nodes[span_id] = node
            order.append(span_id)
            continue
        if kind == "span_end":
            node = nodes.get(span_id)
            if node is None:
                continue                  # 只有结束没有开始：日志被截断了，跳过
            for key, value in event.items():
                if key in ("kind", "span_id", "parent_id"):
                    continue
                node[key] = value         # 结束事件上的字段全部并进节点

    # 第二遍才挂子节点。这样与事件顺序无关：并行的两支谁先落盘都对
    roots = []
    for span_id in order:
        node = nodes[span_id]
        parent_id = node["parent"]
        if parent_id and parent_id in nodes:
            parent = nodes[parent_id]
            parent["children"].append(node)
        if not parent_id:
            roots.append(node)     # 没父的才是树根；父不在日志里的不挂也不当根
    return {"index": nodes, "roots": roots}
```

返回值里两个键。`index` 是全部节点，按编号查。`roots` 是树根。

一轮任务跑下来，`roots` 里应该正好一个节点。多出来的，要么是父节点丢了，要么是日志被截断过。

注意它**不依赖事件顺序**：并行那两条腿谁先落盘都行，`parent_id` 会把它们挂到对的位置。**换个读法，不需要重写事实。**

## 12.1.6 存进数据库

树拼出来了，放哪儿？两个选择。先把这几个词交代掉。

JSONL 是一行一个 JSON 的文件，第 6 章那本流水账就是这个格式。SQLite 是一个小数据库，整个库就是磁盘上的一个文件。P95 是把耗时从小到大排队，95% 的请求比这个数快。聚合查询是把数据分组，算平均、算分位数这类活。

- **继续放 JSONL？** 追加合适，但问「哪个工具 P95 最慢」要把全部日志读一遍，成本迟早不能忍。
- **放 SQLite。** 一张 `spans` 表、一列一个字段；聚合查询是它本行：`SELECT name, AVG(duration_ms) FROM spans GROUP BY name`。

但要守住上一条判据：**trace 库是投影，所以它必须能从日志重建。**

```python
# harnex/observability/trace.py（续）—— 从日志重建 trace 库：删了也不心疼
import sqlite3


def rebuild_trace(db_path, sessions_dir):
    """丢掉旧库，从全部 JSONL 重放一遍。任何时刻都可执行。

    这里用到第 6 章的 load_all_sessions(sessions_dir)：它把每个会话的
    「事件列表 + 会话 id」一个一个交出来。
    """
    # 最常见的报错是 sqlite3.OperationalError：db_path 的目录不存在
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS spans")   # 重建就是不认旧数据，先清空
    conn.execute("""CREATE TABLE spans (
        span_id TEXT PRIMARY KEY, parent_id TEXT, session_id TEXT,
        node TEXT, name TEXT, duration_ms INTEGER,
        tokens_in INTEGER, tokens_out INTEGER, status TEXT)""")
    rows = 0
    for events, session_id in load_all_sessions(sessions_dir):
        tree = project_trace(events)
        for node in tree["index"].values():
            conn.execute("INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?)",
                         (node["id"], node["parent"], session_id, node["node"],
                          node["name"], node["duration_ms"],
                          node["tokens_in"], node["tokens_out"], node["status"]))
            rows += 1
    conn.commit()
    conn.close()                                # 不关的话文件一直被占着
    return rows
```

**「随时可重建」不是口号，是可验证的性质**：升级 schema 就 `rebuild_trace()`。数据对不上也重建。schema 是表的字段清单。你永远不会遇到「日志和看板哪个是真的」。因为看板**从来就不是真的**，它只是日志的一件衣服。

你手写的这套，和行业标准是同一个形状。OpenTelemetry 是一套公开的观测数据标准，各家工具都认它。它为 GenAI（生成式 AI）定的语义约定管的是名字：字段怎么起、叫什么，大家都按同一套来。里面的 `invoke_agent` / `chat` / `execute_tool` 就对应本节的 `turn` / `llm` / `tool`；属性名 `gen_ai.usage.input_tokens` 对应 `tokens_in`。**把「一次 LLM 调用」当成一个 span，是这个问题唯一自然的解法。**

所以那些平台（LangSmith、Langfuse、Datadog）替你做的事，无非三件。**统一的 span 规范、现成的可视化、不用自己维护存储。** 可视化就是把数据画成图和页面。手写一遍再看它们。哪一块它替我省了事、哪一块它逼我按它的形状来，你就能说清了。

## 这一节的边界

- **没有采样。** 采样就是只留一部分、不全记。本节假设 trace 全量落下。真上手量，体积很可观：OTel 说 AI 负载的观测数据量能到传统服务的 10–50 倍。
- **没有跨进程关联，也不存敏感内容。** 跨进程指另一段程序里跑的那部分，子 Agent 的 trace 是第 9 章的延伸。密码、用户隐私这类内容要遮掉，那叫脱敏，是第 15 章的事。

树有了，接下来要用它。下一节拿一个真失败，沿着这棵树往下走。
