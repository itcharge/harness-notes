# harnex/exec/verify.py —— 执行后回读：把「我以为成了」变成「我看到成了」
from pathlib import Path

WORKDIR = Path.cwd().resolve()


def _resolve(rel: str) -> Path:
    """复用第 4 章的路径边界：越界直接抛 ValueError。"""
    target = (WORKDIR / rel).resolve()
    if target != WORKDIR and WORKDIR not in target.parents:
        raise ValueError(f"路径越界：'{rel}' 不在工作目录内")
    return target


def expect_exists(args: dict) -> str:
    """检查路径是否存在。用于验证「产物应该已经生成」这类动作。"""
    rel = args["path"]
    target = _resolve(rel)
    if target.exists():
        return f"已确认：'{rel}' 存在。"
    return (f"未确认：命令虽然成功了，但 '{rel}' 并不存在。"
            f"退出码只能说明命令正常结束，不代表产物真的生成了。"
            f"请检查构建配置、输出目录，或上一步的输入是否正确。")


def expect_contains(args: dict) -> str:
    """检查文件里是否包含指定文本。用于验证「内容改对了」。"""
    rel, keyword = args["path"], args["keyword"]
    target = _resolve(rel)
    if not target.exists():
        return f"未确认：'{rel}' 不存在，无法检查内容。"
    text = target.read_text(encoding="utf-8", errors="replace")
    if keyword in text:
        return f"已确认：'{rel}' 里包含 '{keyword}'。"
    return (f"未确认：'{rel}' 里没有找到 '{keyword}'。"
            f"可能是写错了位置，或者那段文本已经被改掉了。")
