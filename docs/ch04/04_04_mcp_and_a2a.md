# 4.4 MCP 与 A2A：把工具搬进独立进程

## 4.4.1 什么时候拆成独立进程

到这里，工具还是 **你自己进程里的一个函数**。它跑得很快（一次函数调用），但代价是：

- **它崩了，你的循环跟着崩。** 一个工具里的死循环、内存泄漏、段错误，都会带走整个 Harnex。
- **它必须用 Python 写。** 如果团队用 Go 写了一个内部 CLI，那它是没法直接做成 `handler` 的。
- **它不能复用现成的生态。** 别人已经写好并维护的工具，你得抄一遍。

当一个工具满足下面任意一条时，「搬出去」就开始划算：

| 信号         | 说明                  |
| ---------- | ------------------- |
| 它可能崩、可能卡   | 独立进程崩了，循环只是收到一次错误返回 |
| 它是另一门语言写的  | 只要能说协议，什么语言都行       |
| 它有独立的依赖与版本 | 各自装各自的包，互不污染        |
| 别人已经写好了    | 直接接入，不用重写           |
| 它需要跑在别处    | 换 HTTP 传输，工具可以不在本机  |

代价也要说清楚：**每次调用多一次序列化和一次跨进程往返。** 所以「工具很少、都是你自己写的短函数」时，本地函数就是更优解。**这不是「必须用 MCP」，而是「愿不愿意为隔离和复用付这笔开销」。**

## 4.4.2 协议看懂这些就够

MCP（Model Context Protocol）把上面那件事标准化了。你只需要知道四件事：

1. **它是一套 JSON-RPC 协议**：client（你的 harness）和 server（放工具的进程）之间互发 JSON 消息。
2. **三种能力**：`tools`（能调用的动作）、`resources`（能读取的数据）、`prompts`（预置的提示模板）。本章只用 `tools`。
3. **两种传输**：`stdio`（server 是本地子进程，走标准输入输出）和 `HTTP`（server 在远端，走网络）。**本地工具用 stdio，远程工具用 HTTP，别的都一样。**
4. **一份自描述清单**：每个工具的名字、描述、参数 JSON Schema，由 server 对外提供——**正好就是 4.1 节 `Tool` 需要的那三样**。

第 4 点最关键：**MCP 的工具描述格式，和 4.1 节设计的 `Tool` 是同一套东西。** 这不是巧合——MCP 在设计时，就是照着「给模型看的工具清单」来的。

## 4.4.3 最小的服务端

用官方 Python SDK 把一个工具挂上 MCP，只需要几行：

```python
# harnex/tools/mcp/fs_server.py —— 把文件工具搬进独立进程
from mcp.server.fastmcp import FastMCP

from tools_fs import apply_patch as patch_impl, fs_read as read_impl, fs_write as write_impl

server = FastMCP("harnex-fs")


@server.tool()
def fs_read(path: str = ".") -> str:
    """读取工作目录里的文件内容，或列出目录下有哪些文件。"""
    return read_impl({"path": path})


@server.tool()
def fs_write(path: str, content: str) -> str:
    """新建一个文件。目标文件已存在时会失败，请改用 apply_patch。"""
    return write_impl({"path": path, "content": content})


@server.tool()
def apply_patch(path: str, old: str, new: str) -> str:
    """在文件里精确替换一段文本，old 必须唯一。"""
    return patch_impl({"path": path, "old": old, "new": new})


if __name__ == "__main__":
    server.run()          # 默认走 stdio：由 harness 作为子进程拉起
```

三个细节值得留意：

- **工具名和本地保持一致。** 函数叫 `fs_read` / `apply_patch`，不叫 `fs_read_tool`——搬走之后，模型看到的名字不该变。
- **函数签名变成了「具名参数」而不是 `args` 字典。** MCP server 这一侧的参数是**它自己的接口**，由 SDK 生成 JSON Schema 交给客户端；你的工具实现内部收 `args` 字典，只是这个进程里的私事。
- **它的 docstring 就是 description。** SDK 直接读 docstring 当描述——**4.2 节的描述工程，在这里是唯一的信息来源**，写含糊了，harness 那侧收到的就是一条含糊的描述。

## 4.4.4 远程工具进同一个注册表

客户端要做的事，是**把远程工具「翻译」成本地的 `Tool` 对象**，再注册进同一个注册表。

翻译分三步，和 4.4.3 的服务端正好对上：

1. **拉起子进程**，拿到两根管道：一根收它的输出，一根往里发指令。
2. **问它「你会哪些工具」**，服务端回一份清单。
3. **把清单里每一条装成本地 `Tool`**：名字、描述、参数原样搬过来，只把「执行」那一栏换成「转发给它」。

下面这段代码做的就是这三步。

```python
# harnex/tools/mcp/client.py —— 把 MCP server 的工具接进注册表
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools import Tool


class McpServer:
    """启动一个 MCP server 子进程，把它的工具清单翻译成 Tool 注册进注册表。"""

    def __init__(self, command: str, args: list, scopes: list):
        self.command, self.args, self.scopes = command, args, scopes
        self._stack = AsyncExitStack()          # 记下要关的东西，退出时按相反顺序关掉

    async def attach(self, registry) -> None:
        # 第 1 步：拉起子进程。read / write 是两根管道，一根收它的输出，一根往里发指令
        params = StdioServerParameters(command=self.command, args=self.args)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()        # 握手：确认协议版本、交换各自能力

        # 第 2、3 步：问它有哪些工具，逐条翻译成 Tool
        for info in (await self._session.list_tools()).tools:
            registry.register(Tool(
                name=info.name,
                description=info.description,
                parameters=info.inputSchema,       # MCP 给的 JSON Schema，直接可用
                handler=self._proxy(info.name),    # 执行那一栏换成「转发给它」
                scopes=self.scopes,                # 权限仍由本地决定，见下
            ))

    def _proxy(self, name: str):
        """给某个远程工具造一个本地执行函数：收下参数，转过去，再把结果转回来。"""
        async def call(args: dict) -> str:
            result = await self._session.call_tool(name, args)
            return "\n".join(part.text for part in result.content if part.type == "text")
        return call
```

**`_proxy` 这一层看着多余，其实少不掉。** 注册表调 handler 时只递一个 `args` 字典，它不知道这次要调哪个工具；而 MCP 的调用要两个参数：工具名 + 参数。所以每注册一个远程工具，就单独造一个函数，把名字存在函数里。

**`scopes` 是从本地传进去的，不是 server 说了算。** 服务端清单里就算写着「我需要 fs:write」，也不代表它就能拿到——这里用的是你 `McpServer(...)` 时传的那一份。**权限的判断永远留在 harness 这一侧**，这是 4.1 节「默认拒绝」的延伸：工具在哪跑不重要，能不能动手由本地定。

装配线于是变成这样（`build_registry()` 得先加个 `exclude` 参数，被点名的工具不装）：

```python
async def main():
    # 文件工具已搬进独立进程：本地不再装它们，否则 attach() 会撞上重名（4.1 的「重名拒」）
    registry = build_registry(exclude={"fs_read", "fs_write", "apply_patch"})
    fs = McpServer("python", ["-m", "tools.mcp.fs_server"], scopes=["fs:read", "fs:write"])
    await fs.attach(registry)                                     # 文件工具从独立进程接进来
    print(await run("帮我看看 harness 目录里有哪些文件", registry))
```

`["-m", "tools.mcp.fs_server"]` 是子进程的启动命令，等于在项目根目录执行 `python -m tools.mcp.fs_server`。

**必须带 `-m`。** `fs_server.py` 开头要 `from tools_fs import ...`，而这个文件在 `tools/mcp/` 下面。直接 `python tools/mcp/fs_server.py` 启动时，Python 只把 `tools/mcp/` 放进搜索路径，找不到根目录的 `tools_fs.py`。换成 `-m`，当前目录本身就在搜索路径上，两个都能找到（和第 3 章 3.2 节是同一个道理）。

**「搬」是搬走，不是复制**——本地和远程各留一份，模型菜单里就冒出两个功能重叠的工具：同一件活有两个入口，它容易挑错那个。

## 4.4.5 拆出去之后循环怎么接

只有一样东西要改：**调用它的地方得写 `await`**。

为什么非等不可？因为跨进程通信本质是 I/O——消息发出去，要等对面处理完回过来。MCP 官方 SDK 把这类接口全写成了 `async`，你只有 `await` 它这一条路。**这不是风格选择，是 SDK 定的。**

于是注册表里躺着两种 handler：本地工具是普通函数，调完立刻有结果；MCP 工具是 `async` 函数，得等。注册表得两种情况都接得住（`tools/registry.py` 中 `call()` 的变化，其余方法与 4.1 节相同，顶部加 `import inspect`）：

```python
class ToolRegistry:
    ...
    async def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：没有名为 {name} 的工具。可用工具：{', '.join(sorted(self._tools))}"
        try:
            result = tool.handler(args)
            if inspect.isawaitable(result):        # 问一句「要 await 吗」：MCP 工具要，本地工具不要
                result = await result
        except Exception as exc:
            return f"错误：{tool.name} 执行失败（{type(exc).__name__}: {exc}）"
        return result if isinstance(result, str) else str(result)
```

循环里多一个 `await`：

```python
async def run(user_input: str, registry: ToolRegistry) -> str:
    ...
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        result = await registry.call(call.function.name, args)   # 只多了这一个 await
```

（CLI 那层跟着改一行：`asyncio.run(run(q, reg))`——由它开事件循环，把 `run()` 跑起来。**异步会顺着调用链往上传染**：`run()` 里 `await` 了东西，`run()` 自己就得是 `async`，调用它的地方也得跟着改。这是 `async` 的规矩，不是缺陷。）

`inspect.isawaitable` 那一行是这里的关键设计：**注册表不关心工具在哪**——在本地就同步调用，在别的进程就异步等待。于是**本地工具和 MCP 工具可以混在同一个注册表里**，循环对它们的处理完全一致。

> 这里还有一个顺带的好处：`run()` 变成 `async` 之后，第 11 章的流式输出（边生成边显示）就有了落脚点。**流式输出的前提，是整条链路本来是异步的。**

到这里，本章的目标形态出现了：

```text
工具 = 一个 MCP server ＋ 一份自描述清单 ＋ 一份本地权限声明
```

- **内核循环**：只知道注册表和 `registry.call()`
- **工具进程**：可以崩、可以用别的语言写、可以跑在别的机器上
- **权限**：由 harness 在注册那一刻决定给不给

这套结构，是第 20 章「把自己写的工具和技能包发布给别人」的基础——**能被别人接进自己的 harness，前提是它本来就是一个可独立运行的进程，加一份清单。**

## 4.4.6 两个 Agent 怎么互相调用

最后补一个名词，只讲分工，不展开实现。

MCP 解决的是「**Agent ↔ 工具**」：让 Agent 接上动作。而 **A2A**（Agent2Agent）解决的是「**Agent ↔ Agent**」：让一个 Agent 把任务委托给另一个 Agent。

两者的边界很好记：

|       | MCP          | A2A                    |
| ----- | ------------ | ---------------------- |
| 连接的两端 | Agent ↔ 工具   | Agent ↔ Agent          |
| 传递什么  | 一次动作的调用与结果   | 一个任务的目标与进展             |
| 谁负责决策 | 你的 Agent     | 被委托的那个 Agent           |
| 典型场景  | 读文件、跑命令、查数据库 | 「把这个调研交给那个专做搜索的 Agent」 |

最容易被看漏的是「谁负责决策」那一行。MCP 里，工具不会自己想办法：你说读 `a.txt`，它就读 `a.txt`，读不到就报错，不会自作主张换个文件。A2A 里，你只给一个目标（「把这个调研做完」），具体查什么、查几轮、什么时候算完，全由对方那个 Agent 定。

**什么时候需要 A2A？** 当你想把一整类任务（连同判断权）交给另一个独立的 Agent 时。「连同判断权」是关键词——如果你只想让它执行一个动作，那是 MCP 的活，别为了用 A2A 而用 A2A。

这一节只需要你知道它存在、知道边界在哪。**第 9 章「规划与长任务」会回答另一个更常被问到的问题：什么时候才该拆多 Agent——答案是「多数时候不该」。**
