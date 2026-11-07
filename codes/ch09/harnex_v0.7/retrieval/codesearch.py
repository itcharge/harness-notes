# harnex/retrieval/codesearch.py —— 精确搜索优先
import subprocess

ROOT = "."


def code_search(args: dict) -> str:
    """用 ripgrep 在仓库里精确搜索。args: {pattern: str, glob?: str, max_results?: int}"""
    pattern = str(args.get("pattern", "")).strip()
    if not pattern:
        return "错误：pattern 不能为空。"
    max_results = int(args.get("max_results", 30))
    argv = ["rg", "--line-number", "--no-heading", "--color", "never", pattern, ROOT]
    glob = args.get("glob")
    if glob:
        argv += ["--glob", str(glob)]
    try:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return "错误：搜索超时（10 秒）。请把 pattern 写得更具体。"
    if proc.returncode == 1:
        return (
            f"没有匹配 {pattern} 的内容。"
            "可以换一个关键词、去掉 glob 限制，或先用 fs_read 看一下目录结构。"
        )
    if proc.returncode != 0:
        return f"错误：搜索失败（退出码 {proc.returncode}）：{proc.stderr.strip()[:200]}"
    lines = proc.stdout.splitlines()
    body = "\n".join(lines[:max_results])
    if len(lines) > max_results:
        body += f"\n（共 {len(lines)} 处匹配，此处显示前 {max_results} 处）"
    return body
