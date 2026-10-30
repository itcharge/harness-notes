# harnex/tools/mcp/fs_server.py —— 把文件工具搬进独立进程
from mcp.server.mcpserver import MCPServer

from tools_fs import apply_patch as patch_impl, fs_read as read_impl, fs_write as write_impl

server = MCPServer("harnex-fs")


def _safe(fn, args: dict) -> str:
    """工具里抛的异常，SDK 只回一句「Error executing tool」，原因会丢——自己兜住。"""
    try:
        return fn(args)
    except Exception as exc:
        return f"错误：{type(exc).__name__}: {exc}"


@server.tool()
def fs_read(path: str = ".") -> str:
    """读取工作目录里的文件内容，或列出目录下有哪些文件。"""
    return _safe(read_impl, {"path": path})


@server.tool()
def fs_write(path: str, content: str) -> str:
    """新建一个文件。目标文件已存在时会失败，请改用 apply_patch。"""
    return _safe(write_impl, {"path": path, "content": content})


@server.tool()
def apply_patch(path: str, old: str, new: str) -> str:
    """在文件里精确替换一段文本，old 必须唯一。"""
    return _safe(patch_impl, {"path": path, "old": old, "new": new})


if __name__ == "__main__":
    server.run()          # 默认走 stdio：由 harness 作为子进程拉起
