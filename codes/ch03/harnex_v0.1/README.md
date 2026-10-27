# harnex v0.1 —— 第 3 章，可单独运行

这个目录是到本章为止能跑的一份代码，包含前面章节已经写好的模块。
`from llm import chat` 用的是第 2 章的 [`llm/client.py`](llm/client.py)。
文件直接放在目录下。最终项目 `codes/harnex/` 才套 `src/harnex/`，因为那是一个要安装的包。

在本目录运行（需要已安装 `openai`，并设置 `DEEPSEEK_API_KEY`）：

```bash
PYTHONPATH=. python loop/agent.py
```

书里的版本号是另一把尺（第 3 章七十行记作 v0.3）。
这里从第 3 章那份七十行 Agent 的 v0.1 起算，每章加 0.1，第 12 章为 v1.0。

| 本目录中的文件 | 对应最终 harnex |
| --- | --- |
| `loop/agent.py` | `codes/harnex/src/harnex/loop/agent.py` |
| `llm/client.py` | `codes/harnex/src/harnex/llm/client.py` |

为了让上面的导入能在本目录跑通，另外补了这些薄封装：

- `llm/__init__.py`
