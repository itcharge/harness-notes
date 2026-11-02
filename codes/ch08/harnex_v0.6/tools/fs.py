# harnex/tools/fs.py —— 文件工具，全部限制在工作目录内
from pathlib import Path

WORKDIR = Path.cwd().resolve()          # 启动时钉死的工作目录


def _resolve(rel: str) -> Path:
    """把模型给的相对路径解析到工作目录内；越界抛 ValueError。"""
    target = (WORKDIR / rel).resolve()  # resolve() 会展开 .. 与软链接
    if target != WORKDIR and WORKDIR not in target.parents:
        raise ValueError(f"路径越界：'{rel}' 不在工作目录内")
    return target


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
