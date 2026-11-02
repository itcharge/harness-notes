# harnex/tools/build_registry.py —— 装配线：把工具装进注册表
from exec.shell import shell
from exec.verify import expect_contains, expect_exists
from retrieval.codesearch import code_search
from retrieval.search_tool import search_docs
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


def verify_tools(add) -> None:
    """两个回读工具：确认「我以为成了」变成「我看到成了」。"""
    add(_tool(
        name="expect_exists",
        description=("回读：确认某个路径真的存在。建目录、生成产物、写文件之后用它验收——"
                     "命令退出码为 0 不代表文件真的在那个位置、那个名字上。"),
        properties={"path": {"type": "string", "description": "相对工作目录的路径"}},
        handler=expect_exists,
        scopes=["fs:read"],
        required=["path"],
    ))

    add(_tool(
        name="expect_contains",
        description=("回读：确认某个文件里真的包含一段文本。改完文件之后用它验收——"
                     "确认改对了位置，而且旧内容确实被换掉了。"),
        properties={"path": {"type": "string", "description": "相对工作目录的路径"},
                    "keyword": {"type": "string", "description": "应当出现的文本"}},
        handler=expect_contains,
        scopes=["fs:read"],
        required=["path", "keyword"],
    ))


def retrieval_tools(add) -> None:
    """一个查文档，一个查源码。装配线里加一行 retrieval_tools(add)。"""
    add(_tool(
        name="search_docs",
        description=(
            "在项目知识库里检索相关段落，返回带编号和来源的原文。"
            "当你被问到项目文档、规范、历史决策相关的问题，"
            "而当前上下文里没有这些信息时使用。"
            "如果问题涉及多个概念的关联，分几轮检索："
            "先查最直接的那个概念，再用它返回的关键词构造下一轮的 query。"
            "闲聊、或答案就在当前对话里时，不要调用它。"
        ),
        properties={
            "query": {"type": "string", "description": "检索用的关键词或短句"},
            "k": {"type": "integer", "description": "返回几块，默认 4"},
        },
        handler=search_docs,
        scopes=["kb:read"],
        required=["query"],
    ))

    add(_tool(
        name="code_search",
        description=("在仓库里按正则精确搜索代码，返回「文件:行号:内容」。"
                     "知道要找的符号名或字符串时优先用它——它比向量检索准，"
                     "也比一层层读文件快。不知道叫什么、只知道大概意思时，才用 search_docs。"),
        properties={
            "pattern": {"type": "string", "description": "正则或字面量"},
            "glob": {"type": "string", "description": "限定文件名，如 '*.py'"},
            "max_results": {"type": "integer", "description": "最多返回几条，默认 30"},
        },
        handler=code_search,
        scopes=["repo:search"],
        required=["pattern"],
    ))


def build_registry(exclude: set | None = None) -> ToolRegistry:
    """装配工具。exclude 里点名的工具不装——它们要搬进 MCP 进程，本地再装就重名了。"""
    skip = set(exclude or ())
    registry = ToolRegistry(granted_scopes={"fs:read", "fs:write", "kb:read", "proc:exec", "repo:search", "time:read"})

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

    exec_tools(add)
    verify_tools(add)
    retrieval_tools(add)

    return registry
