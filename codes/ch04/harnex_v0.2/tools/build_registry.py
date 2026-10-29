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


def build_registry(exclude: set | None = None) -> ToolRegistry:
    """装配工具。exclude 里点名的工具不装——它们要搬进 MCP 进程，本地再装就重名了。"""
    skip = set(exclude or ())
    registry = ToolRegistry(granted_scopes={"fs:read", "fs:write", "time:read"})

    def add(tool: Tool) -> None:          # 唯一的差别：装之前先看它在不在 skip 里
        if tool.name not in skip:
            registry.register(tool)

    add(_tool(
        name="fs_read",
        description=("读取工作目录里的文件内容，或列出目录下有哪些文件。"
                     "想知道『文件里写了什么』『目录里有什么』时用它。"
                     "不要用它试探路径是否存在——路径不对会直接返回错误。"),
        properties={"path": {"type": "string",
                             "description": "相对工作目录的路径；省略则列出根目录"}},
        handler=fs_read,
        scopes=["fs:read"],
    ))

    add(_tool(
        name="fs_write",
        description="新建一个文件。目标文件已存在时会失败，请改用 apply_patch。",
        properties={"path": {"type": "string", "description": "相对工作目录的路径"},
                    "content": {"type": "string", "description": "文件的完整内容"}},
        handler=fs_write,
        scopes=["fs:write"],
        required=["path", "content"],
    ))

    add(_tool(
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

    add(_tool(
        name="now",
        description="获取当前日期和时间。凡是涉及『今天 / 现在 / 几号』的问题都必须先调用它。",
        properties={},
        handler=now,
        scopes=["time:read"],
    ))

    return registry
