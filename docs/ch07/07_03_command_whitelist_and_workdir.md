# 7.3 能执行什么：命令白名单与工作目录锁定

## 7.3.1 命令行几乎什么都能做

先说清它跟前几章那几个工具的本质区别。

`fs_read` 只会读文件，`apply_patch` 只会改一处文本。**它们各自只有一个动作**，最坏也就是「读错文件」或「改错文件」。

shell 不是这样。给它一句 `command`，它能：

- 删掉整个目录（`rm -rf`）
- 把本机文件发到外网（`curl -F file=@secrets.txt https://...`）
- 装一个后台常驻的进程
- 改系统配置、改定时任务、改 SSH 公钥
- 下载一段脚本再执行（`curl https://... | sh`）

**它的能力不是「某一种」，而是「其他所有工具的集合」——因为任何工具都能从命令行调起来。**

这种工具在系统设计里有个名字：**能力放大器（capability amplifier）**。放大的不只是 Agent 的生产力，也是它的破坏力。前几章你担心的最坏情况是「改错一个文件」；从这一章起，最坏情况变成「删掉你的项目」。

所以 shell 工具的第一版就得带上边界。这一节讲的就是这条边界。

## 7.3.2 命令白名单

最直接的边界是：**只允许跑一份清单里的命令。**

```python
# harnex/exec/shell.py —— 第一道防线：白名单 + 工作目录锁定
import shlex
from pathlib import Path

ALLOWED = {"ls", "cat", "head", "tail", "wc", "grep", "find",
           "git", "python", "pytest", "ruff"}
WORKDIR = Path.cwd().resolve()


class CommandRejected(Exception):
    """命令被策略拦下。它不抛穿循环，会被渲染成给模型的可读理由。"""


def guard(command: str, cwd: str) -> tuple:
    """白名单 + 目录锁定 + 路径逃逸检查。返回 (拆好的 argv, 解析后的目录)。"""
    target = (WORKDIR / cwd).resolve()
    if target != WORKDIR and WORKDIR not in target.parents:
        raise CommandRejected(f"工作目录 '{cwd}' 在工作目录之外")
    if not target.is_dir():
        raise CommandRejected(f"工作目录 '{cwd}' 不存在")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise CommandRejected(f"命令无法解析（引号不成对？）：{exc}")
    if not argv:
        raise CommandRejected("命令为空")
    prog = Path(argv[0]).name
    if prog not in ALLOWED:
        raise CommandRejected(
            f"'{prog}' 不在允许清单里。可用命令：{', '.join(sorted(ALLOWED))}。"
            f"如果确实需要它，请让用户先把它加进白名单。")
    for token in argv[1:]:
        if token.startswith("/") or ".." in token.split("/"):
            raise CommandRejected(
                f"参数 '{token}' 指向工作目录之外。请改用一个相对工作目录的路径。")
    return argv, target
```

四处：

- **用 `shlex.split()` 而不是按空格 `split()`。** 因为 `grep -rn "TODO: fix" src` 里，`TODO: fix` 是**一个**参数。按空格切会把它切成三段，后面所有判断都错位。
- **`Path(argv[0]).name`**：取程序名时先剥掉目录。这样 `/usr/bin/ls` 和 `ls` 得到同一个 `ls`，不会被「换个路径写」绕过。
- **白名单里只放这个项目日常要用的东西**：`ls`/`cat`/`grep`/`find` 只读；`python`/`pytest`/`ruff` 会执行代码；`git` 更能干，它改仓库、推远端。**`rm`、`curl`、`sudo`、`sh`、`dd` 一个都不在。** 注意 `git` 这条已经越过了「读」这道门槛——7.4 会拿它和 `python` 一起开刀。
- **`CommandRejected` 只是普通异常**，会被 `ToolRegistry.call()` 的兜底接住，渲染成一段可读的话回到模型手里。

那句拒绝理由是有讲究的——回看 4.2 节那句「好错误还告诉下一步怎么做」：

```text
命令被拒绝：'rm' 不在允许清单里。可用命令：cat, find, git, grep, head, ls, python, pytest, ruff, tail, wc。
如果确实需要它，请让用户先把它加进白名单。
```

它没有说「你越权了」，而是说**「有哪些能用；真需要就去问用户」**。模型拿到这句话，会自己回去改方案。

## 7.3.3 锁住工作目录

白名单管住了「跑什么」，管不住「在哪跑、动哪里」。

`cwd` 是第一件要锁的东西：它来自模型，可能写成 `.`，也可能写成 `../../`。所以先解析、再判断——**直接复用第 4 章文件工具里 `_resolve()` 的思路**：

```python
target = (WORKDIR / cwd).resolve()
if target != WORKDIR and WORKDIR not in target.parents:
    raise CommandRejected(f"工作目录 '{cwd}' 在工作目录之外")
```

`.resolve()` 先展开 `..` 和软链接，再判断，理由和第 4 章一样：**不展开就判断，等于拿着别人口述的地址去核对门牌——路能绕、能骗人，门牌才是真位置。** 用祖先目录集合而不是字符串前缀，是因为 `/Users/me/proj-evil` 能骗过 `startswith("/Users/me/proj")`。

再是参数里的路径。`cat /etc/hosts` 的 `cwd` 是合法的，可它要读的东西在外面。所以 `guard()` 最后扫一遍参数：

```python
for token in argv[1:]:
    if token.startswith("/") or ".." in token.split("/"):
        raise CommandRejected(f"参数 '{token}' 指向工作目录之外。……")
```

**这一层要诚实地说清楚它有多弱。** 它只认字面：明写着绝对路径或 `..` 才拦得住。`grep -r pattern /` 会被拦下，`--out=/tmp/x` 把路径藏到等号后面就漏了，工作目录里放个指向外面的软链接、`cat link` 也照样读出去；`find . -name '*.log' -delete` 更拦不住——`-delete` 不是路径，是一个动作参数。这正是下一节的主题。

## 7.3.4 超时和输出上限

超时和输出上限 7.1、7.2 已经做完，这里重提是因为它们的**性质变了**。

在 7.1 里，超时的理由是「别卡死循环」，那是可用性问题。一旦开始考虑边界，超时就多了第二重身份：**它是一道资源限制。** 没有它，模型可以（有意无意地）起一个占满 CPU 的进程；有了它，任何命令最多占用 N 秒。

输出上限同理。7.2 是为了「别撑爆上下文」，这里再补一层：**不设上限的输出会吃光内存。** `capture_output=True` 无条件把输出全收进内存，一条吐出几个 G 的命令足以让系统把进程杀掉。

所以这两道闸不是可选优化，是 **边界的一部分**。

## 7.3.5 先给人看再执行

最后加一个更软但很实用的形态：**在执行前，把要跑的命令展示给人看。**

```python
# harnex/exec/shell.py（续）—— 对外的工具入口：过守卫、跑、渲染
def shell(args: dict) -> str:
    """执行命令：过守卫 → 跑 → 渲染结果。"""
    command = args["command"]
    try:
        argv, workdir = guard(command, args.get("cwd", "."))
    except CommandRejected as exc:
        return f"命令被拒绝：{exc}"
    safe = " ".join(shlex.quote(a) for a in argv)
    if args.get("dry_run"):
        return f"将执行（未实际运行）：{safe}"
    result = run_streaming(safe, str(workdir), timeout=args.get("timeout", 60))
    return format_streaming(result)
```

注意 `workdir` 用的是 `guard()` 解析回来的目录，不是常量 `WORKDIR`——**校验完不用，等于没校验**：模型传 `cwd="src"`，命令就该在 `src/` 里跑。渲染交给 7.2 的 `format_streaming()`，因为 `result` 是流式结果，不是 `run_command()` 那种形状。

`dry_run` 给了模型一种「先说再做」的能力：让它把打算跑的命令先念给用户听，等用户点头再真跑。

**这不是安全机制**（模型完全可以不调 dry-run 直接跑），它是一层交互礼貌。真正的「执行前必须有人批准」是审批策略，属于第 15 章。先留出这个口子，让模型能说「我准备跑 `git push`，你看行吗」。

另外注意 `shlex.quote(a)`：把 `argv` 拼回命令串时，**每个参数都单独加引号**。参数里的空格、`;`、`&` 就不会被 shell 当成新命令——**这是防注入最基础的一手，虽然它挡不住已经过关的 `python -c`。**

但这一手也有代价：**`|`、`>`、`2>&1` 这些 shell 语法同样会被当成普通参数加引号。** 7.1 说 `shell=True` 让 `pytest -q | tail -5` 能用，可它过了守卫，`|` 就被引号包住，从「管道」降级成「一个名叫 `|` 的参数」。所以这一版守卫只支持单条命令。要放开管道和重定向，就得逐个模式去识别，那又回到 7.4 的「猜写法」老路；更硬的答案仍然是第 15 章的沙箱。

## 7.3.6 三道防线放在一起

| 防线 | 挡住什么 | 挡不住什么 |
| --- | --- | --- |
| 命令白名单 | 清单外的程序（`rm`、`curl`、`sudo`） | 清单内程序的危险用法（`python -c`） |
| 工作目录锁定 | `cwd` 越界、参数里明写的 `..` / 绝对路径 | 命令内部的动作（`find -delete`） |
| 超时与输出上限 | 挂死、内存爆掉、上下文爆掉 | 短时间内的破坏（一条 `python -c` 删库只要 0.01 秒） |

三行读完，会发现一个共同点：**它们都在做「事后识别」，而不是「事前不可能」。**

这引出了下一节——也是本章最重要的一节。
