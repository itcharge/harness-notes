# 7.6 交互式与长驻进程（点到为止）

## 7.6.1 两类不好处理的命令

到 7.5 为止，shell 工具处理的都是 **同一类命令**：跑起来、干活、结束、返回。

但有两类命令不符合这个模型，而且都很常见——只是**结束的方式不一样**。

**第一类：要跟人对话的。**

```text
$ npm init
package name: (my-project)        ← 在等你打字
```

```text
$ git commit
# 打开一个编辑器，等你写完提交信息再保存退出
```

```text
$ ssh deploy@prod
deploy@prod's password:           ← 在等你输密码
```

它们的共同点是：**停下来，等一个从标准输入来的回答。** 在终端前坐着的人会看到提示、敲字、回车。但 harness 里没有人——**这个等待永远不会结束。**

**第二类：设计上就不结束的。**

```text
$ npm run dev
  Local:   http://localhost:5173/     ← 起来了，然后一直跑着
```

```text
$ python -m http.server 8000
Serving HTTP on 0.0.0.0 port 8000 ...  ← 一直服务，直到被 kill
```

它们**不打算退出**。你要的不是「它跑完」，而是「它起来了，并且活着」——这两件事在返回值的层面完全不同。

## 7.6.2 不要等键盘输入

先说第一类，它有个很轻的解法。

留意 7.2 那段代码里的一行：

```python
stdin=subprocess.DEVNULL
```

它把命令的标准输入接到一个空设备上。效果是：**命令一旦试图读输入，立刻读到 EOF。**

这带来的行为差异很关键：

```text
不接 DEVNULL：
  $ python -c "input('name: ')"
  （进程挂起，等着人打字，直到超时被 kill）

接上 DEVNULL：
  $ python -c "input('name: ')"
  name: Traceback (most recent call last):
    ...
  EOFError: EOF when reading a line
  （立即失败退出，exit code 1）
```

**同样是失败，但一个是「莫名其妙地超时」，一个是「明确的报错」**——差别完全在可诊断性上。第二种返回模型读得懂，能自己改方案；第一种让模型只能重试。

不过这种体面不是白来的。换成 `npm init`，`DEVNULL` 只能换来「停在第一个提示上直接退出」（实测 npm 10：exit 1，一个字的原因都不给）。**它保证的只是「不挂死」；报错清不清楚，得看命令自己怎么写。**

除了 `DEVNULL`，还有两条配套：

- **白名单里对这几条命令加参数要求。** `git commit` 必须带 `-m`（在 `guard()` 里检查），`npm init` 必须带 `-y`。**把「不要交互」在工具层强制下来**，而不是靠描述里写「请不要用交互式命令」。
- **超时提示里加一句猜测。** 7.1 那句「它可能在等待输入，或者陷入了死循环」就是干这个的。模型拿到这句话，会想到「我是不是该加个 `-y`」。

这三条合起来，能把绝大多数交互式命令的事故降下来。**但它们治不了根**：有些命令就是必须交互（`ssh` 输密码、`sudo` 提权），这些命令在白名单里根本不该出现——它们属于「人来跑」的范畴。

## 7.6.3 一直开着的进程

长驻进程没那么好绕。它的难点不在「怎么启动」，而在**「启动之后怎么继续跟它打交道」**。

先想清楚你要什么。`npm run dev` 起来之后，你可能要做三件事：

1. **看它有没有起来**：读它的输出，看到 `Local: http://localhost:5173/`
2. **跟它说话**：往里输一个命令（有些 dev server 支持按 `r` 重载）
3. **结束它**：跑完这次任务就该关掉

用「跑一条命令、拿一个返回」的模型表达这三件事，很别扭。你需要的是把终端本身做成一个**可以反复交互的对象**：

```text
terminal = start("npm run dev")
read(terminal)          → "Local: http://localhost:5173/"
write(terminal, "r")    → 触发重载
read(terminal)          → "page reload src/main.tsx"
kill(terminal)          → 结束
```

这不是四条独立命令，是**一个持久对象上的四个方法**。DeepSeek Harness 里管这东西叫 `ctx.terminals`，背后是 PTY（伪终端）——一个让程序以为自己连着一个真终端的接口，这样它才会用「交互模式」而不是「批处理模式」跑。

**PTY 是必要的**：很多程序发现 stdout 不是终端（只是个管道）时，行为会变——不输出彩色、不显示进度条，甚至切到完全不同的输出格式。你想要「和人在终端里跑一样」的效果，就得给它一个假终端。

## 7.6.4 为什么不放进主线

到这里你大概能感觉到它有多麻烦。本章不做，理由是三条，都很实在：

**一是成本。** PTY 是跨平台差异最大的地方之一——Linux 有 `pty` 模块，Windows 要另外一套。还要处理输出缓冲（有些程序不 flush 就看不到）、僵尸进程清理、终端尺寸等一堆细节。

**二是复杂度。** 有了持久终端，就要管理「开着几个终端、哪个对应哪个任务、退出时怎么全关掉」。这是**状态管理**，跟本章「无状态的命令执行」差着量级。

**三是不必需。** 八成任务不需要交互——跑测试、看状态、执行脚本，都是「跑完就结束」的。为两成场景引入两倍复杂度，不划算。

**第 19 章会重新拾起它**：计算机使用（computer use）就是「持续跟一个图形界面交互」，那时持久终端和持久会话绕不过去。

## 7.6.5 一个够用的做法

不做真终端，但有个折中能覆盖大多数「起个服务试一试」的场景——**后台起 + 输出落文件 + 需要时读回来**：

```python
# harnex/exec/shell.py —— 最小后台任务：起、读、停
import os
import signal
import subprocess
from pathlib import Path

BG_DIR = Path("sessions/background")


def _next_handle() -> str:
    """句柄只增不减：旧日志不会被清掉，编号接着往下数，撞不上还在跑的任务。"""
    nums = [int(p.stem[3:]) for p in BG_DIR.glob("bg-*.log") if p.stem[3:].isdigit()]
    return f"bg-{max(nums, default=0) + 1}"


def start_background(command: str, cwd: str) -> str:
    """把命令丢到后台跑，输出落到文件。返回句柄，供后面查询与停止。"""
    BG_DIR.mkdir(parents=True, exist_ok=True)
    handle = _next_handle()
    log = BG_DIR / f"{handle}.log"
    with log.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
        )
    (BG_DIR / f"{handle}.pid").write_text(str(proc.pid), encoding="utf-8")
    return f"已在后台启动 {handle}（pid {proc.pid}），输出写入 {log}。"


def read_background(handle: str, tail_lines: int = 40) -> str:
    """读后台任务的输出：和 7.2 一样只给尾部，并且说清一共多少行。"""
    log = BG_DIR / f"{handle}.log"
    if not log.exists():
        return f"错误：没有名为 {handle} 的后台任务。"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return "（暂无输出）"
    tail = "\n".join(lines[-tail_lines:])
    if len(lines) > tail_lines:
        return f"注意：输出共 {len(lines)} 行，以下只显示最后 {tail_lines} 行。\n{tail}"
    return tail


def stop_background(handle: str) -> str:
    """停掉后台任务：按 pid 找到整个进程组，发一次 TERM 信号。"""
    pid_file = BG_DIR / f"{handle}.pid"
    if not pid_file.exists():
        return f"错误：没有名为 {handle} 的后台任务。"
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        pid_file.unlink()
        return f"{handle} 已经自己退出了，顺手清掉了句柄。"
    pid_file.unlink()
    return f"已停止 {handle}（pid {pid}）。"
```

三个设计选择：

- **`start_new_session=True`**：让后台进程另起一个会话，自己当组长。不这么做，它就跟父进程挤在同一个进程组里：父进程那一组收到信号，它跟着遭殃；更糟的是 `killpg` 找到的会是**你自己那个组**——按一下「停」，把 harness 自己也停了。这一手顺带给「停」铺了路：整棵树都在新组里，一次信号全停。
- **输出落文件，不落内存。** 一个跑几小时的服务，输出不能一直攒在内存里；落文件之后，「读」就变成了普通的文件读，天然带上了 7.2 那套截断逻辑。
- **有句柄，没有真交互。** 这个版本能「起、读、停」，但**不能往里写**。够用来验证「服务起来了、响应正常吗」，不够用来驱动一个需要输入的程序。

**句柄用自增序号，不用进程号**：`bg-1` 比 `bg-48213` 好念，模型也不容易抄错。编号只增不减——日志留着，数就回不去，新任务撞不上还在跑的那个。代价是旧日志会堆在 `sessions/background/` 里，得上清理策略。

**注意它写在 `sessions/` 底下**——和第 6 章的会话日志共用同一个根目录。后台任务的输出也是「发生过的事」，它的去向本该和日志一致。

## 7.6.6 这一章能做什么

回看这一章给 Harnex 装上的东西：

- 能跑命令，并拿到**结构化的判决**（退出码、输出、耗时、超时）
- 能**边跑边看**，大输出只留尾部
- 有**三道边界**：白名单、目录锁定、超时与上限
- 知道**验证**：退出码 0 之后再回读一次
- 对交互式和长驻进程有一张**路线图**（`DEVNULL` + 后台句柄；PTY 留到第 19 章）

**它是第一个能执行任意程序的 Harnex。** 前面几章的工具，动作都是我们一个个写出来的：读文件、写文件、装技能。这一章交出去的是一个「什么都可能」的入口——装依赖、跑测试、起服务，全由它自己决定。而这也意味着，它第一次有了把东西弄坏的能力。

你在 7.3、7.4 看到的那些绕法不是危言耸听——**它们是真的，而且字符串过滤真的拦不住。** 这正是第 15 章存在的理由：到那时你会发现，「我确实需要沙箱」这个结论不是被说服出来的，是自己撞出来的。

下一章换一个方向：Harnex 能执行了，但它每次只能看眼前这一点。**当信息多到读不完的时候，它该从哪里入手去找？**
