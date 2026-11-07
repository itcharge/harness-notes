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
