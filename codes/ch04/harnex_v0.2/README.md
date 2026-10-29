# harnex v0.2 —— 第 4 章，可单独运行

这个目录是到本章为止能跑的一份代码，包含前面章节已经写好的模块。
`from llm import chat` 用的是第 2 章的 [`llm/client.py`](llm/client.py)。
文件直接放在目录下。最终项目 `codes/harnex/` 才套 `src/harnex/`，因为那是一个要安装的包。

在本目录运行（需要已安装 `openai` 和 `mcp`，并设置 `DEEPSEEK_API_KEY`）。`mcp` 装本章验证过的版本：`pip install mcp==2.3.0`；1.x 的 `FastMCP` 在 2.x 已改名 `MCPServer`，装错版本 `tools/mcp/fs_server.py` 会 import 失败。用 `-m` 从目录本身启动，不要写成 `python loop/agent.py`，那样 `from llm import chat` 会找不到模块：

```bash
python -m loop.agent
```

版本从第 3 章那份七十行 Agent 的 v0.1 起算，每章加 0.1，第 12 章为 v1.0。

| 本目录中的文件 | 对应最终 harnex |
| --- | --- |
| `loop/agent.py` | `codes/harnex/src/harnex/loop/agent.py` |
| `tools/registry.py` | `codes/harnex/src/harnex/tools/registry.py` |
| `tools/misc.py` | `codes/harnex/src/harnex/tools/misc.py` |
| `tools/fs.py` | `codes/harnex/src/harnex/tools/fs.py` |
| `tools/build_registry.py` | `codes/harnex/src/harnex/tools/build_registry.py` |
| `tools/mcp/fs_server.py` | `codes/harnex/src/harnex/tools/mcp/fs_server.py` |
| `tools/mcp/client.py` | `codes/harnex/src/harnex/tools/mcp/client.py` |
| `llm/client.py` | `codes/harnex/src/harnex/llm/client.py` |

为了让上面的导入能在本目录跑通，另外补了这些薄封装：

- `llm/__init__.py`
- `tools/__init__.py`
- `tools_fs.py`
- `tools_misc.py`
- `build_registry.py`
- `loop/build_registry.py`
