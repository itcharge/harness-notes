# 9.2 待办清单模式：先规划，再执行

## 9.2.1 先列清单再动手

上一节把三种坏法摊开了：走偏、打转、假完成。前两种丢的是目标和进度。这一节先补这两样，验收留到 9.3。

做法分两步，都不新鲜。两步用的都是前面已经有的东西。

**第一步，规划。** 先让模型把一句话的目标，翻成一张排好顺序的子任务列表。做法是问一次模型，让它按固定格式回答。这就是第 2 章讲过的「结构化输出」：不要它写一段散文，要它返回 JSON。JSON 是一种用花括号和方括号摆数据的写法，程序读起来不费劲。

```json
[
  {"task": "列出 package.json 里的全部依赖", "done_when": "拿到依赖名列表，共 N 条"},
  {"task": "找出每个依赖在源码里的引用点", "done_when": "产出 依赖→引用位置 的对照表"},
  {"task": "改写或删除没有引用点的依赖",
   "done_when": "package.json 里不再有零引用的条目"},
  {"task": "跑测试确认没坏", "done_when": "pytest -q 退出码 0，且用例数不少于改前"}
]
```

`done_when` 这一列先记住，9.3 要用它，9.4 讲它该怎么写。它回答的是「这一项做到什么样算完」。

为什么单开一次调用做规划，而不是直接在循环里让模型「一步一步想」？因为「想」出来的东西留在回复文本里。回复文本和工具结果一样，会被后面的内容一层层盖住。**计划得写成一个能反复读的东西，光在回复里说一遍不算。** 这也是第 2 章那条一般规律。要被后面几步依赖的东西，都该变成结构化数据。别留在自然语言里。

**第二步，执行。** 逐项做，逐项勾销。清单**常驻上下文**，每一轮都能看到自己走到第几项了。上下文就是这一轮摆在模型眼前的那堆内容，9.1 讲过，它只有这一堆可看。

## 9.2.2 清单记在日志里

清单要常驻，先得决定它存在哪。最直觉的做法是在 `run_task()` 里开一个局部变量：

```python
todos = []                     # ← 别这么做
```

`run_task()` 是干一件完整任务的那个函数，9.2.5 会看到它的样子。局部变量是函数跑起来时临时存东西的地方，函数一结束就没了。

模型调一次工具就改它。这个做法有三个问题，每一个都能在第 6 章找到对应的话：

**问题一，进程一崩就没了。** 进程就是程序跑起来的那一份，关掉或崩掉，它占的那块内存就清空了。第 6 章的规矩是：日志才是唯一作数的记录，内存里的状态只是它的一个影子。把清单塞进变量里，等于在账本外面另记一本小账，两边迟早对不上。

**问题二，它不进上下文。** 你得每一轮手动把它拼进消息里。**而「每一轮都记得拼」正是长任务里最容易漏的动作**。漏一轮，那一轮就退回到上一节的状态。

**问题三，翻不回去。** 三天后想问「它当时打算做几步」「第几步改了主意」，答不上来。

清单像出门带的路线单。写在纸上，丢了还能照着重画一张；记在脑子里，一忙就忘，事后也没法回头查。

所以清单按老规矩办：**它是日志里的一种新事件，当前状态是投影出来的。** 事件就是日志里的一行记录，一行只记一件事。投影是拿这些记录算出「现在是什么样」，不是另存一份。

新增事件类型 `todo_update`，载荷是 **整张清单的一份快照**。载荷是这条事件里带的数据，快照是整张清单的完整拷贝。

```text
{"seq":14,"ts":1758021503.2,"kind":"todo_update",
 "items":[{"id":1,"task":"列出依赖","done_when":"...","status":"done"},
          {"id":2,"task":"找引用点","done_when":"...","status":"doing"}, ...]}
```

`project_todos()` 只看 **最后一条** `todo_update`。它取那一条的 `items` 当当前清单。它不会把历史上所有 `todo_update` 合起来。为什么存全量快照而不是只存改动，下面讲代码时说。

这条决定顺手解决了一个常见的错误做法——「计划只存在第一轮上下文里」。清单是 **每轮重新画一遍** 的，根本不存在「第一轮」这个说法。**它不是被记住的，是被重新画出来的。**

## 9.2.3 把清单显示给模型

清单已经在日志里了，可模型看不见日志。要让它看见，得先算出当前清单，再摆成一段文字。后一步叫渲染，就是让一堆数据变成能读的文本。

```python
# harnex/planning/todos.py —— 待办清单：状态在日志里，每轮投影渲染进上下文
STATUS = {"todo": "[ ]", "doing": "[>]", "done": "[x]", "failed": "[!]"}
MARK = {"todo": "待办", "doing": "进行中", "done": "已完成", "failed": "失败"}


def project_todos(events: list[dict]) -> list[dict]:
    """当前清单 = 最后一条 todo_update 的 items；没有则返回空清单。"""
    latest: list[dict] = []
    for event in events:
        if event["kind"] == "todo_update":
            latest = event["items"]
    return latest


def render_todos(items: list[dict]) -> str:
    """把清单渲染成给模型看的一段文本。它每轮都会被拼进系统提示。"""
    if not items:
        return "（当前没有待办清单）"
    lines = ["当前待办清单："]
    for item in items:
        mark = STATUS.get(item.get("status", "todo"), "[ ]")
        lines.append(f"{mark} {item['id']}. {item['task']}")
        if item.get("done_when"):
            lines.append(f"      完成标准：{item['done_when']}")
        if item.get("note"):
            lines.append(f"      备注：{item['note']}")
    done_count = sum(1 for item in items if item.get("status") == "done")
    lines.append(f"进度：{done_count}/{len(items)} 已完成")
    return "\n".join(lines)
```

`render_todos()` 的输出长这样，大约 40–120 token。token 是模型计价的单位，可以粗略当成「一小段文字」。

```text
当前待办清单：
[x] 1. 列出 package.json 里的全部依赖
      完成标准：拿到依赖名列表，共 N 条
[>] 2. 找出每个依赖在源码里的引用点
      完成标准：产出 依赖→引用位置 的对照表
      备注：已扫 src/ 下 12 个文件
[ ] 3. 改写或删除没有引用点的依赖
      完成标准：package.json 里不再有零引用的条目
[ ] 4. 跑测试确认没坏
      完成标准：pytest -q 退出码 0，且用例数不少于改前
进度：1/4 已完成
```

## 9.2.4 加待办和改状态

摆出来只是让模型看见。清单还得能被它改，所以要做成工具。工具就是模型能调的动作，9.1 讲过。两个就够：一个写整张清单，一个改某一项。

```python
# harnex/planning/todos.py（续）—— 把两个清单工具绑到某一份日志上
def make_todo_tools(log) -> tuple:
    """返回 (set_todos, update_todo)，两者都把状态写回日志。"""

    def set_todos(args: dict) -> str:
        """写入或整体替换待办清单。items 为 [{task, done_when}, ...]。"""
        raw_items = args.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return "错误：items 必须是非空列表，每一项至少要有一个 task 字段。"
        clean_items = []
        for i, item in enumerate(raw_items):
            if not isinstance(item, dict) or not item.get("task"):
                return f"错误：第 {i + 1} 项缺少 task 字段。"
            clean_items.append({"id": i + 1,
                                "task": str(item["task"]),
                                "done_when": str(item.get("done_when", "")),
                                "status": "todo"})
        log.append("todo_update", items=clean_items)
        return f"已写入 {len(clean_items)} 项待办：\n" + render_todos(clean_items)

    def update_todo(args: dict) -> str:
        """更新某一项的状态。status 取 todo / doing / done / failed。"""
        if args.get("status") not in STATUS:
            allowed = " / ".join(STATUS)
            return f"错误：status 只能是 {allowed}。"
        items = project_todos(log.events())
        index = int(args.get("index", 0))
        if index < 1 or index > len(items):
            return f"错误：清单里没有第 {index} 项，当前共 {len(items)} 项。"
        target = items[index - 1]
        target["status"] = args["status"]
        if args.get("note"):
            target["note"] = str(args["note"])
        log.append("todo_update", items=items)
        return "已更新：\n" + render_todos(items)

    return set_todos, update_todo
```

四处细节：

- **两个工具都写全量快照。** 日志里每次 `todo_update` 都是整张清单的一份拷贝。`project_todos()` 只要取最后一条。这比记「改了什么」简单得多，也不会出现「丢了一条改动，状态从此对不上」。清单最多几十项，这点重复不值得省。
- **`set_todos` 强制重编 `id`。** 模型给回来的 id 可能重复也可能跳号；重编一遍，`update_todo` 的 `index` 就永远有效。
- **`update_todo` 先验货再落盘。** 不合法时返回带上下文的错误（「当前共 4 项」），而不是抛异常。这是 4.2 节那条「好错误给下一步」。落盘就是写进日志。
- **状态四个值，不用布尔。** 布尔只有「是」和「否」两个值，表达不了「正在做」。`doing` 让界面能显示「正在做第 2 步」。`failed` 让下一节的重试有个落点。

## 9.2.5 每一轮重新显示

两个工具会写了，还得让它们在每一轮真的出现。这一节把清单接进主循环，也就是 9.1 说的那个循环：看情况、做动作、再看情况。

```python
# harnex/loop/agent.py 片段 —— Harnex v0.7：清单每轮重建，拼进系统提示
async def run_task(goal: str, registry, log: SessionLog, system: str = BASE_PROMPT) -> str:
    log.append("user_message", content=goal)
    set_todos, update_todo = make_todo_tools(log)
    # 同一进程里第二次进任务时，两个工具已经在表里了——4.1 那条「重名拒」会拦下重装
    installed = {schema["function"]["name"] for schema in registry.schemas()}
    if "set_todos" not in installed:
        registry.register(Tool("set_todos", "写入或替换整张待办清单。开始一个多步任务时先调它。",
                               {"type": "object", "required": ["items"],
                                "properties": {"items": {"type": "array"}}},
                               set_todos, ["plan:write"]))
        registry.register(Tool("update_todo", "更新清单某一项的状态。每完成一项都要调它。",
                               {"type": "object", "required": ["index", "status"],
                                "properties": {"index": {"type": "integer"},
                                               "status": {"type": "string"},
                                               "note": {"type": "string"}}},
                               update_todo, ["plan:write"]))

    for _ in range(MAX_STEPS):
        messages = project(log.events())
        todos_text = render_todos(project_todos(log.events()))
        system_with_todos = system + "\n\n" + todos_text
        messages.insert(0, {"role": "system", "content": system_with_todos})
        msg = chat(messages, tools=registry.schemas())
        ...
```

有两处跟清单不直接相关，但不交代就会踩坑。

**一是权限。** 两个工具申请的是 `plan:write`。这个标记写在工具的登记表里，说明它能改哪一类东西。清单写的是日志，不是文件，不该借 `fs:write` 的名义。装配线是启动时把工具一个个装进表里的那段代码。它要把这个范围一并授予。不然 4.1 那条「未获授予」会在注册时就把它们拦下来。

**二是入口。** 终端里把 `run_turn()` 换成 `run_task()`。终端就是敲命令的那个窗口。两者只差两处：开头一段装工具的代码，中间一句拼清单。`run_turn` 是「一轮问答」，`run_task` 是「一个任务」。

真正要动手写的，就是循环开头那两行。每轮开始，清单从日志投影出来、渲染成一段文本、拼在系统提示后面。

这点开销值得。**它是数据，不是叮嘱。** 这比在提示里写一句「别忘了原始目标」管用。模型面对的不是一句要求，而是一张带进度的状态表。至于十几项清单占的那点 token，在 6.2 节那张预算表里连一格都占不上。

**它还顺手治了「打转」。** 第 2 项标成 `doing`，备注里写着「已扫 src/ 下 12 个文件」。这两条信息每轮都在眼前。模型再想读同一个配置文件时，这张表会提醒它「这一带已经扫过了」。打转的根子是分不清「新的」和「看过的」。清单正好把这两者划开了。**它把「我做过了什么」从十几条散落的工具结果，压成了一份随时能读的摘要。**

两个工具的描述也要照 4.2 节的要求写清「什么时候用」：

```text
set_todos：写入或替换整张待办清单。开始一个多步任务时调用；
           执行中发现计划需要调整，也调用它重写整张。
           单步任务不要调用——直接做。
update_todo：更新清单某一项的状态。开工前先把该项标成 doing，
             完成后标成 done 或 failed，并带上 note。
```

「单步任务不要调用」这句不是客套。不说清，模型碰上「帮我看下这个函数是干嘛的」也会先建一张三项清单。那是 9.4 节要算的一笔成本。

**清单也是给人看的进度条。** 同一段 `render_todos()` 的文本，第 11 章的控制台也会用上。它会变成一张能点的列表。**你没为界面多写一行代码**——清单本来就在日志里，界面只是另一种投影。

**「改计划」的痕迹是白送的。** 每次写入都是一条事件。把所有 `todo_update` 按 `seq` 排开，就能看它怎么一步步调整计划。9.4 节会说「允许改计划，但要留痕」。留痕这件事在这里已经办完了，日志里那条事件就是痕。

## 9.2.6 还没解决的问题

清单能治「走偏」和「打转」，治不了「假完成」。清单能告诉你「第 3 项标成了 done」。可**标成 done 这件事是模型自己说的**。上一节那个模型就是这么干的：没做成，却调了 `update_todo(status="done")`。

那这个 done 算不算数，谁说了算？下一节。
