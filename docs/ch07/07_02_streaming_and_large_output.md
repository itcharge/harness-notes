# 7.2 流式输出捕获与大输出处理

## 7.2.1 跑很久，屏幕没反应

7.1 的 `run_command()` 有个毛病：**它要等命令彻底跑完才肯返回。** 不算 bug，是真难受。

跑一次 `pytest -q` 是 0.4 秒，你没感觉。但用户让你「装一下依赖」——`npm install` 跑三分钟。这三分钟里：

- 用户盯着屏幕，什么都没发生
- 模型在等工具返回，也不能做别的
- 真要装错了包，也得到第三分钟跑完才知道

真实的终端里不是这样：`npm install` 一行一行往下滚，你能看到它在装第几个包、卡在哪一步。**harness 的「实时感」就来自把这种滚动搬到界面上。**

要让它滚出来，就不能用「跑完再取」的 `subprocess.run()`，得用能 **边跑边读** 的 `Popen`。

## 7.2.2 边跑边读

```python
# harnex/exec/shell.py —— 流式执行：每一行都回调出去
import subprocess
import threading
import time


def run_streaming(command: str, cwd: str, timeout: float = 120.0,
                  on_line=None, tail_lines: int = 40) -> dict:
    """流式跑一条命令：逐行回调，只把尾部若干行留给模型。"""
    started = time.monotonic()
    proc = subprocess.Popen(
        command, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", bufsize=1,
    )
    lines: list = []

    def pump() -> None:
        for raw in proc.stdout:              # 一直读到 EOF
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line:
                on_line(line)                # 推给界面

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        timed_out = True
    reader.join(timeout=2.0)
    return {
        "exit_code": None if timed_out else proc.returncode,
        "tail": "\n".join(lines[-tail_lines:]),
        "total_lines": len(lines),
        "truncated": len(lines) > tail_lines,
        "tail_lines": tail_lines,
        "duration": round(time.monotonic() - started, 2),
        "timed_out": timed_out,
    }
```

四个关键点：

- **读和等分成两条线。** 主线程用 `proc.wait(timeout=...)` 守时间，另一个线程专管读。两件事挤进一条线程的话，`for raw in proc.stdout` 会一直阻塞到命令结束——**超时根本轮不到执行**。
- **`stderr=subprocess.STDOUT`**：这一节把错误输出也合进同一条流，因为用户看滚动时想要的是一条时间线，不是两条交错的流。给模型的最终结果里，7.1 那种 `stdout`/`stderr` 分开的写法更清楚——**这不矛盾：界面要合、模型要分。**
- **`stdin=subprocess.DEVNULL`**：不给命令接标准输入。这不是为了好看——它让「等输入的命令」直接读到 EOF 然后退出，而不是挂在那里等一个永远不会来的回车。7.6 节会展开。
- **`bufsize=1` 配 `text=True`**：行缓冲、按文本读。这样 `on_line` 拿到的是完整的一行，不是半个字节。

`on_line` 就是「推给用户」的那个口子。本章先把它留成一个回调，具体怎么接到前端（终端逐行打印、WebSocket、还是 SSE）是第 11 章的内容。**接口先定下来，接线以后再说。**

## 7.2.3 正常输出和错误输出

先说个容易忽略的结构：一个 Agent 跑起来，界面上其实有 **两条流**。

一条是 **模型输出流**——它一边想一边吐字，用户看到「我先看看这个文件……」慢慢写出来。另一条是 **命令输出流**——`pytest` 一行一行往下滚。

这两条流在时间上是交错的：模型说「我先跑一下测试」→ 命令流开始滚 → 滚完了 → 模型接着说「测试通过了，接下来……」。

怎么把它们合到同一个界面上、又不显得乱，是第 11 章要认真处理的问题。这一节只需要知道：**命令流的数据源就是这个 `on_line` 回调。** 有了它，上层才有东西可合。

## 7.2.4 输出有几万行

第二个问题更重：**输出可能大得离谱。**

一段真实的编译日志：

```text
$ npm run build
...
（共 31284 行）
```

三万多行。如果把它们全塞进 `tool_result` 事件、再原样带进下一轮对话，会发生什么？

按一行约 12 个 token 粗算，31284 行大约是 **37 万 token**。而第 6 章算过，一个 128k 窗口，输入的安全线在 70% 左右——也就是 9 万 token 上下。**一次编译，上下文就冲到安全线的四倍。**

这不是「有点浪费」，是「任务当场结束」。

所以规矩是：**工具返回给模型的内容必须有上限。** 上面代码里的 `tail_lines=40` 就是这个上限——**只留最后 40 行。**

## 7.2.5 为什么留最后一段

截断的位置不是随便定的。三种截断各有各的适用场景：

| 策略 | 保留 | 适合什么 |
| --- | --- | --- |
| 保头 `head` | 前 N 行 | 输出结构在上面、下面是重复数据的（表头 + 十万行数据） |
| 保尾 `tail` | 后 N 行 | 错误和结论通常在最后的（编译、测试、安装） |
| 保关键行 | 含 `error` / `failed` / `warning` 的行 | 日志类输出 |

**默认选保尾**，因为绝大多数命令行工具的结论都在末尾——`1 failed, 3 passed`、`Build complete`、`error: ...`。而开头往往只交代「它是怎么开始的」，信息量小得多。

但只给尾巴还不够，模型得知道 **自己看的只是尾巴**。所以返回值里除了 `exit_code`，还得带上两个数：总共多少行、有没有被截。

```text
exit_code   1
total_lines 31284
truncated   True
```

渲染成文本时，这层信息要显式写出来：

```text
命令失败（exit 1），耗时 18.3s
注意：输出共 31284 行，以下只显示最后 40 行。
输出：
...
error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.
    at src/api.ts:42:18
```

那句「共 31284 行，以下只显示最后 40 行」很关键。没有它，模型会以为这就是全部输出，然后在「只有 40 行」的前提下做判断。有了它，模型至少知道两件事：**输出被截了**，以及**可以用更精确的命令再问一次**——比如 `npm run build 2>&1 | grep -i error | head -20`。

对应地，渲染函数也得认这套形状——7.1 的 `format_for_model()` 读的是 `stdout` / `stderr`，而流式结果交出来的是 `tail` / `total_lines` / `truncated` / `tail_lines`。**形状不同，就各配一个渲染函数**：

```python
# harnex/exec/shell.py（续）—— 流式结果另配一个渲染函数：形状不同，读法就不同
def format_streaming(result: dict) -> str:
    """把流式结果渲染成模型读的文本：判决在前，尾部输出在后。"""
    if result["timed_out"]:
        return (f"命令超时，已强制终止（耗时 {result['duration']}s）。"
                f"它可能在等待输入，或者陷入了死循环——不要原样重试。")
    verdict = "命令成功（exit 0）" if result["exit_code"] == 0 else \
              f"命令失败（exit {result['exit_code']}）"
    parts = [f"{verdict}，耗时 {result['duration']}s"]
    if result["truncated"]:
        parts.append(f"注意：输出共 {result['total_lines']} 行，"
                     f"以下只显示最后 {result['tail_lines']} 行。")
    if result["tail"].strip():
        parts.append("输出：\n" + result["tail"].rstrip())
    return "\n".join(parts)
```

硬把 `tail` 塞进 `stdout` 的位置，只会换来一个 `KeyError`——**接口变了，消费它的那一段就得跟着变**。

## 7.2.6 另外两种缩小办法

截断是「跑完之后从结果里挑」。还有两种办法更省，直接在**源头**收窄。

**一是让命令自己少说话。** 这靠工具的 description 去引导：与其让模型跑完 `npm run build` 再读三万行日志，不如在描述里就写上「日志很长时，优先用 `grep`、`tail`、`-q` 这类参数收窄输出」。

**二是加一个输出字节上限。** 行数不是唯一的维度——一行 minified 的 JS 可能有二十万字符，40 行就是八百万字符。所以除了 `tail_lines`，还要有一个总字节数的封顶（比如 64KB），超了就硬切。**两道闸，一道管行数、一道管字节。**

## 动手：跑起来

到这一步，shell 工具已经能用了。把它注册进 Harnex，描述写成：

```text
在项目里执行一条 shell 命令。需要看文件列表、搜索内容、跑测试、运行脚本时用它。
命令的输出可能很长，请尽量用 grep / tail / -q 这类方式收窄。
命令不会结束或需要交互输入时，请改用非交互的写法，否则会被超时终止。
```

装进装配线。工具一多，`build_registry()` 本身也该分组——执行类归一组、回读类归一组，别让它长成两百行：

```python
# harnex/tools/build_registry.py 片段 —— 第 7 章：执行类工具归一组
def exec_tools(add) -> None:
    """shell。add 就是 build_registry 里那个「看 skip 再装」的小函数。"""
    add(_tool(
        name="shell",
        description=(
            "在项目里执行一条 shell 命令。需要看文件列表、搜索内容、跑测试、"
            "运行脚本时用它。命令的输出可能很长，请尽量用 grep / tail / -q 这类方式收窄。"
            "命令不会结束或需要交互输入时，请改用非交互的写法，否则会被超时终止。"
        ),
        properties={
            "command": {"type": "string", "description": "要执行的完整命令"},
            "cwd": {"type": "string", "description": "相对工作目录的执行目录，默认 '.'"},
            "dry_run": {"type": "boolean", "description": "为 true 时只回话展示，不真跑"},
            "timeout": {"type": "integer", "description": "超时秒数；读操作 10–30，构建与测试 120–300"},
        },
        handler=shell,
        scopes=["proc:exec"],
        required=["command"],
    ))
```

装配线里加一行 `exec_tools(add)` 就装上了。

它申请的是 `proc:exec`——这个工具真的会启动进程，和 `fs:write` 不是一回事。装配线的授予范围里得加上它，否则注册会被 4.1 那条「未获授予」直接拦下。

然后让它做这三件事，逐个看返回：

```text
你> 列出当前目录下的文件
你> 在 src 里搜一下所有 TODO
你> 跑一下 python -c "print(1 + 1)"
```

三条命令覆盖了 `ls`、`grep`、`python -c` 三种形态。它们现在真的能跑了。

但请注意一件刚发生的事：**Harnex 现在能跑任何命令了。** 你试的是无害的 `ls`；同一条通道上，它也能跑 `rm -rf`——如果一旦删错目录，没有后悔药可吃。下一节开始画地为牢。
