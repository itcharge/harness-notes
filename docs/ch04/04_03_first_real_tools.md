# 4.3 第一批正式工具：读、写、改

前两节讲原则，这一节写代码：工具是一份带说明书的记录，注册表是它的家，描述要写到模型不会用错，失败要返回带下一步的错误。**Harnex 从这一节起，真的能替你动文件了。**

代码分两个模块：`tools/fs.py` 放文件工具，`tools/misc.py` 放时间工具和 4.2 节那个教具。仓库根下的 `tools_fs.py`、`tools_misc.py` 只是把它们转出来，供平铺导入。

## 4.3.1 只能改工作目录里的文件

工具层最容易出事的地方是路径。模型给出的 `path` 来自自然语言，它可能是 `src/main.py`，也可能是 `/etc/hosts`，还可能是 `../../../../etc/passwd`。

所以文件工具做的第一件事不是读，而是 **解析**：

```python
# harnex/tools/fs.py —— 文件工具，全部限制在工作目录内
from pathlib import Path

WORKDIR = Path.cwd().resolve()          # 启动时钉死的工作目录


def _resolve(rel: str) -> Path:
    """把模型给的相对路径解析到工作目录内；越界抛 ValueError。"""
    target = (WORKDIR / rel).resolve()  # resolve() 会展开 .. 与软链接
    if target != WORKDIR and WORKDIR not in target.parents:
        raise ValueError(f"路径越界：'{rel}' 不在工作目录内")
    return target
```

三处细节，逐字读一遍：

- **`(WORKDIR / rel).resolve()`** 先把路径拼出来，再**展开**——`..`、软链接、`./` 全都还原成真实位置。不展开就判断，等于拿着别人口头指的路去核对门牌——路可以绕、可以骗人，门牌才是真位置。
- **`WORKDIR not in target.parents`** 是边界检查。用祖先目录集合而不是字符串前缀，是因为 `/Users/me/harness-evil` 能骗过 `startswith("/Users/me/harness")` 这类写法。
- **放行 `target == WORKDIR`**，这样 `fs_read(path=".")` 能列出根目录。

这是**权限最小的落地形态**：不靠提示词请求模型「不要越界」，而是让越界在物理上做不到。第 15 章的沙箱会再叠加更硬的一层（进程级隔离），但「工具自己守好边界」这一层，任何时候都不能省。

## 4.3.2 读、写、改

```python
def _dir_first(path: Path) -> tuple:
    """排序键：目录排在文件前面，同类按名字排。"""
    return (path.is_file(), path.name)


def fs_read(args: dict) -> str:
    """读取文件内容，或列出目录下有哪些文件。path 省略则列出根目录。"""
    rel = args.get("path", ".")
    target = _resolve(rel)
    if not target.exists():
        return f"错误：路径 '{rel}' 不存在。请先用 fs_read(path='.') 看看有哪些文件。"
    if target.is_dir():
        entries = sorted(target.iterdir(), key=_dir_first)
        head = [f"{'[目录] ' if p.is_dir() else ''}{p.name}" for p in entries[:50]]
        more = f"\n…（共 {len(entries)} 项，只列出前 50 项）" if len(entries) > 50 else ""
        return f"{rel}/ 下有 {len(entries)} 项：\n" + "\n".join(head) + more
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"错误：'{rel}' 不是文本文件，无法读取。"


def fs_write(args: dict) -> str:
    """新建文件。修改已有文件请用 apply_patch。"""
    rel, content = args["path"], args["content"]
    target = _resolve(rel)
    if target.exists():
        return (f"错误：'{rel}' 已存在，fs_write 只用于新建文件。"
                f"请改用 apply_patch(path='{rel}', old=..., new=...)。")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已创建 {rel}（{len(content.splitlines())} 行）"


def apply_patch(args: dict) -> str:
    """在文件里精确替换一段文本；old 必须在文件里唯一出现。"""
    rel, old, new = args["path"], args["old"], args["new"]
    target = _resolve(rel)
    if not target.exists():
        return (f"错误：'{rel}' 不存在。请先用 fs_read(path='{rel}') 确认，"
                f"或改用 fs_write 创建它。")
    text = target.read_text(encoding="utf-8")
    hits = text.count(old)
    if hits == 0:
        return f"错误：在 {rel} 里找不到要替换的原文。请先用 fs_read(path='{rel}') 核对空格与缩进。"
    if hits > 1:
        return f"错误：要替换的原文在 {rel} 里出现 {hits} 次，无法定位。请在 old 里多带几行上下文。"
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return f"已修改 {rel}（{len(old.splitlines())} 行 → {len(new.splitlines())} 行）"
```

这里**没有一处 `try/except` 包住 `_resolve()`**。越界时它抛出的 `ValueError` 会被 `ToolRegistry.call()` 的兜底捕获，变成：

```text
错误：fs_read 执行失败（ValueError: 路径越界：'../../etc/hosts' 不在工作目录内）
```

模型照样读得懂，还会自己改路径。**兜底只写一次，所有工具受益**——这就是 4.1 节把异常兜底放进注册表的回报。

三件值得单独看的事：

- **`fs_read` 有默认值，`fs_write` 没有。** `path` 省略时 `fs_read` 列根目录，最坏情况只是读错地方；而 `fs_write` 少传 `path` 或 `content` 就直接报错——**会改状态的工具，永远不要给「聪明」的默认值。**
- **`fs_write` 拒绝覆盖已有文件。** 「改已有文件用 `apply_patch`」这条规矩，不是写在文档里请你遵守，而是**钉在工具里强制执行**：想改文件，只剩一条路。
- **`apply_patch` 的三种失败各自带下一步**，和 4.2 节展示的三条返回一一对应。目录列表也演示了「输出封顶」：截断在 50 项——**工具的返回同样是上下文预算**，一个上万行的目录列表会把模型这一轮的注意力全吃掉。

`tools_misc.py` 里另外两个工具是 `now` 和 4.2 节的教具 `delete_note`：前者示范「没有参数的工具长什么样」，后者示范「好错误 + 抛异常兜底」两条路径。

## 4.3.3 小改动用补丁

| 对比项 | `apply_patch` | 整篇写入            |
| --- | ------------- | --------------- |
| 传输量 | 只发改动的几行       | 整个文件（一次几千 token） |
| 出错面 | 替换失败 = 文件原样不动  | 写一半、内容错了，都可能留下坏文件 |
| 可审性 | diff 一眼看懂改了什么 | 看不出改了哪里         |
| 并发  | 原文变了就失败，不静默覆盖 | 会悄悄盖掉别人的修改      |
| 适用  | 改已有文件         | 新建文件、整篇重写       |

这张表比的是两种改法。本章的 `fs_write` 只做新建；要整篇重写，得先删再建，或者另写一个允许覆写的工具。

**一条实用推论**：模型改代码时应当默认走 `apply_patch`。所以 `apply_patch` 的 description 里必须写明「新建文件请用 `fs_write`」，否则它会在文件不存在时反复重试同一个补丁。

## 4.3.4 装进 Harnex

四个工具装进注册表。先补一个小函数，省掉重复的 `parameters` 外壳：

```python
# harnex/tools/build_registry.py —— 装配线：把工具装进注册表
from tools import Tool, ToolRegistry
from tools_fs import apply_patch, fs_read, fs_write
from tools_misc import now


def _tool(name: str, description: str, properties: dict, handler, scopes: list,
          required: list | None = None) -> Tool:
    """把 JSON Schema 的外壳包起来，注册时只写真正有信息量的部分。"""
    return Tool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties,
                    "required": required or []},
        handler=handler,
        scopes=scopes,
    )


def build_registry() -> ToolRegistry:
    registry = ToolRegistry(granted_scopes={"fs:read", "fs:write", "time:read"})

    registry.register(_tool(
        name="fs_read",
        description=("读取工作目录里的文件内容，或列出目录下有哪些文件。"
                     "想知道『文件里写了什么』『目录里有什么』时用它。"
                     "不要用它试探路径是否存在——路径不对会直接返回错误。"),
        properties={"path": {"type": "string",
                             "description": "相对工作目录的路径；省略则列出根目录"}},
        handler=fs_read,
        scopes=["fs:read"],
    ))

    registry.register(_tool(
        name="fs_write",
        description="新建一个文件。目标文件已存在时会失败，请改用 apply_patch。",
        properties={"path": {"type": "string", "description": "相对工作目录的路径"},
                    "content": {"type": "string", "description": "文件的完整内容"}},
        handler=fs_write,
        scopes=["fs:write"],
        required=["path", "content"],
    ))

    registry.register(_tool(
        name="apply_patch",
        description=("在已有文件里精确替换一段文本。old 必须在文件里唯一出现，"
                     "拿不准就多带几行上下文。新建文件请用 fs_write。"),
        properties={"path": {"type": "string", "description": "相对工作目录的路径"},
                    "old": {"type": "string", "description": "要被替换的原文，必须唯一"},
                    "new": {"type": "string", "description": "替换成的新文本"}},
        handler=apply_patch,
        scopes=["fs:write"],
        required=["path", "old", "new"],
    ))

    registry.register(_tool(
        name="now",
        description="获取当前日期和时间。凡是涉及『今天 / 现在 / 几号』的问题都必须先调用它。",
        properties={},
        handler=now,
        scopes=["time:read"],
    ))

    return registry
```

三处细节：

- **每个工具只申请自己真正需要的那一项权限。** `fs_read` 要不到 `fs:write`，所以就算它被误调，也改不了任何东西。
- **`required` 与默认值一一对应**：`fs_read` 的 `path` 可省，所以不在 `required` 里；`fs_write` 两个参数都必填。
- **教具 `delete_note` 故意没在这里注册。** 它留给你在动手任务 2 里亲手接进去——顺带你得替它决定申请哪个 scope、这场会话该不该授予。它的 `filename` 就写成 `required`，和 4.2 节说的一致。

主循环跟着改一行：

```python
# harnex/loop/agent.py —— Harnex v0.2：循环只认识注册表
import json

from build_registry import build_registry
from llm import chat
from tools import ToolRegistry

MAX_STEPS = 8


def run(user_input: str, registry: ToolRegistry) -> str:
    messages = [{"role": "user", "content": user_input}]
    for step in range(MAX_STEPS):
        msg = chat(messages, tools=registry.schemas())       # 菜单由注册表生成
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = registry.call(call.function.name, args)  # 交给注册表：它负责找到并执行
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


if __name__ == "__main__":
    reg = build_registry()
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", run(q, reg))
```

把第 3 章的 `loop/agent.py` 和这一版放在一起 diff，核心变化只有三处：

| 第 3 章                                    | 本章 v0.2                                |
| ---------------------------------------- | -------------------------------------- |
| `TOOLS = {...}` 手写字典                     | `build_registry()` 自动装配                |
| `chat(..., tools=TOOL_SCHEMAS)`          | `chat(..., tools=registry.schemas())`  |
| `fn = TOOLS[...]` → `result = fn(args)`  | `result = registry.call(name, args)`   |

**熔断、追加顺序、终止判断，一个字都没动。** 循环从「认识两个工具」变成「认识任意多个工具」，代价只有这么一点——这就是 4.1 节那句「可插拔」的实际分量。

（这一版还是同步的。到 4.4 接上 MCP，`registry.call()` 会变成 `async`，循环里多一个 `await`——那是为了等另一个进程的结果，不是为了别的。见 4.4.5。）
