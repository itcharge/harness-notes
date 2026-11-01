# 7.1 子进程执行的最小实现：返回码比自然语言可靠

## 7.1.1 一条命令返回什么

先说清 shell 工具的接口。它的输入只有两样：

```python
{"command": "pytest -q", "cwd": "."}
```

要跑的整条命令，外加一个工作目录。而 **回来的结果不止一段文本——`stdout` 只是其中一样**。

大多数人写第一个 shell 工具，只把命令的输出文本原样返回——毕竟人盯着终端，看到的本来就是一屏字。但模型的处境和人不一样：**人要的是「看到输出」，模型要的是「判断成败」。** 人在终端前混着看没关系；到了工具接口里，这两件事必须分开。

一条命令跑完，至少有四样东西值得回传：

| 字段 | 是什么 | 模型拿它做什么 |
| --- | --- | --- |
| `exit_code` | 进程返回码，0 表示正常结束 | **判断成败的唯一硬信号** |
| `stdout` | 标准输出 | 读结果、读数据 |
| `stderr` | 标准错误 | 读报错信息 |
| `duration` | 耗时 | 判断要不要换策略（太慢了） |

四样里，`exit_code` 最重要，也最容易被漏掉。

## 7.1.2 只看屏幕输出会漏什么

看一个真实场景。你让 Harnex 跑测试，可这个环境里没装 `pytest`：

```text
$ pytest
bash: pytest: command not found
```

注意：这条错误信息走的是 **`stderr`**，而 `stdout` 是 **空的**。如果 shell 工具只回传 `stdout`，模型收到的是一个空字符串。

一段空字符串，怎么解释都说得通。最要命的一种解释是：**「命令没有输出，说明一切正常。」** 于是它回你一句「测试通过」。

再看一种：测试真跑了，也确实失败了，终端上印出来的是这么一段话：

```text
$ pytest -q
FAILED tests/test_parser.py::test_edge - AssertionError
1 failed, 3 passed in 0.4s
```

这段文字里有 `FAILED`，模型大概率能读出来。可「能读出来」得看模型看得细不细、这行字写得显不显眼——**这变成了概率问题。而「过没过」本来就不该是概率问题。**

**所以规矩是：把成败判断从模型手里拿走，交给进程返回码。**

## 7.1.3 用返回码判断成败

不管命令在 `stdout` 上写了什么白话，进程退出时都会给出一个整数：

- **0**：正常结束
- **非 0**：出了问题

这是操作系统定下的约定，任何命令行程序都遵守：`pytest` 测试失败返回 1，`git` 冲突返回 1，`grep` 没搜到也返回 1，`python` 脚本抛异常还是 1。**它没有歧义，不需要理解，也不受语言风格影响。**

所以 shell 工具的第一职责，是把返回码变成一句给模型的判决：

```python
# harnex/exec/shell.py —— 最小子进程执行
import subprocess
import time


def run_command(command: str, cwd: str, timeout: float = 30.0) -> dict:
    """跑一条命令，返回结构化结果；超时也转成返回值，不往外抛。"""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command, shell=True, cwd=cwd, timeout=timeout,
            capture_output=True, text=True, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "",
                "duration": round(time.monotonic() - started, 2),
                "timed_out": True}
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration": round(time.monotonic() - started, 2),
        "timed_out": False,
    }
```

五处细节：

- **`shell=True`** 把整条命令交给系统的 shell 解释，这样 `pytest -q | tail -5` 这种带管道的写法才能用。代价是它同时打开了注入的口子——[7.4 节](07_04_blacklist_vs_sandbox.md)会正面处理这件事。这一节先用最简单的写法把功能跑通。
- **`timeout`** 必须有。少了它，一条 `tail -f` 样的命令会让整个循环永久挂起——这是 shell 工具最经典的一类事故。
- **`capture_output=True`** 把 `stdout` 和 `stderr` 分开接。合在一起的话，模型就分不清哪句是结果、哪句是报错。
- **`errors="replace"`** 让命令输出里混进非 UTF-8 字节时，不至于让整个工具挂掉。
- **它只兜「超时」，不兜全部异常。** `cwd` 不存在、权限不足这类 `OSError` 仍会抛出——那属于「调用环境不对」，不是「命令跑失败了」，该由更外层的注册表兜底转成文本（4.1 节的 `call()` 就是干这个的）。

## 7.1.4 整理成模型能读的文字

结构化结果留在程序里，回给模型的仍然是一段文本——但这段文本是 **加工过的**：

```python
def format_for_model(result: dict) -> str:
    """把结构化结果渲染成模型读的文本：先给判决，再给证据。"""
    if result["timed_out"]:
        return (f"命令超时，已强制终止（耗时 {result['duration']}s）。"
                f"它可能在等待输入，或者陷入了死循环——不要原样重试，"
                f"先想清楚它为什么不会结束。")
    verdict = "命令成功（exit 0）" if result["exit_code"] == 0 else \
              f"命令失败（exit {result['exit_code']}）"
    parts = [f"{verdict}，耗时 {result['duration']}s"]
    if result["stdout"].strip():
        parts.append("输出：\n" + result["stdout"].rstrip())
    if result["stderr"].strip():
        parts.append("错误输出：\n" + result["stderr"].rstrip())
    return "\n".join(parts)
```

回给模型的那段话，第一行不是输出，是判决：**`命令成功（exit 0）`** 或 **`命令失败（exit 1）`**。判断在这里就做完了，模型不用再去 `stdout` 里找线索。

对比一下两种返回，模型接下来的行为完全不同：

```text
只回 stdout（stderr 被丢掉）：
  输出：
  （空）
  → 模型：「命令似乎没有产生有效输出，让我换个方式检查一下。」
     （它连「pytest 没装」这件事都看不到）

回判决 + 证据：
  命令失败（exit 127），耗时 0.02s
  错误输出：
  bash: pytest: command not found
  → 模型：「pytest 没装。我先看看项目用的是哪个测试框架，再决定装哪个。」
     （它直接进入下一步）
```

第二种少了一整轮猜测。**这就是「把判断从模型手里拿走」的具体收益。**

## 7.1.5 超时也是一种结果

`timeout` 在上面那段代码里只是个普通参数，但它值得单独说一节——**它是 shell 工具的必需品，不是可选项。**

没有超时的 shell 工具，迟早会遇到这三类命令：

- **等输入的**：`npm init`（问一堆问题）、`git commit`（不带 `-m` 会弹编辑器）、`ssh`（要密码）。它们安安静静地等一个永远不会来的输入。
- **不会结束的**：`tail -f app.log`、`npm run dev`、`python -m http.server`。它们的工作就是一直跑。
- **真的卡住的**：网络请求没设超时、死锁、等一个不存在的设备。

这三类命令在模型眼里是同一副样子：**不返回。** 用户那边看到的是 Harnex 卡住了，一问三不知。

超时把它变成一条 **可读的结果**：

```text
命令超时，已强制终止（耗时 60.0s）。
它可能在等待输入，或者陷入了死循环——不要原样重试，先想清楚它为什么不会结束。
```

注意最后半句。它不只是告诉模型「超时了」，还 **堵住了模型最蠢的一种反应**：原封不动再跑一次。超时不是网络抖动，重试大概率还是超时。

至于设多少，没有标准答案。经验值：**读操作 10–30 秒，构建与测试 120–300 秒，装依赖看情况**。拿不准就往大了给——超时的代价是任务中断，通常比多跑一会儿贵得多。

## 复杂度收在哪

到这一步，`run_command()` 和 `format_for_model()` 加起来不到 50 行，却已经把 shell 工具的**判断逻辑**做完了：能跑、能判、能超时、还能把结果讲成模型读得懂的话。

还剩两件事没解决：**命令跑到一半，用户什么都看不到**（`capture_output` 得等全部跑完才返回），以及**输出可能大得离谱**（它会把输出整个收进内存）。下一节处理这两个。
