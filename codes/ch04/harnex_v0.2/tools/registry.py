# harnex/tools/registry.py —— Harnex v0.2：可插拔的工具层
import inspect
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    """一个工具 = 名字 + 说明 + 参数 schema + 执行函数 + 权限声明。"""
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], str]
    scopes: list = field(default_factory=list)     # 权限声明：空 = 什么都没申请

    def schema(self) -> dict:
        """转成给模型看的那一项（第 3 章 TOOL_SCHEMAS 里的一项）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具的家：负责注册、校验、取用。循环只跟它打交道，不认识任何具体工具。"""

    def __init__(self, granted_scopes: set):
        self._tools: dict = {}
        self._granted = set(granted_scopes)        # 本次会话被授予的权限范围

    def register(self, tool: Tool) -> None:
        if not tool.scopes:
            raise ValueError(f"拒绝注册 {tool.name}：未声明任何权限（默认拒绝）")
        missing = [s for s in tool.scopes if s not in self._granted]
        if missing:
            raise ValueError(f"拒绝注册 {tool.name}：申请 {missing}，未获授予")
        if tool.name in self._tools:
            raise ValueError(f"拒绝注册 {tool.name}：名字已被占用")
        self._tools[tool.name] = tool

    def schemas(self) -> list:
        return [tool.schema() for tool in self._tools.values()]

    async def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：没有名为 {name} 的工具。可用工具：{', '.join(sorted(self._tools))}"
        try:
            result = tool.handler(args)
            if inspect.isawaitable(result):        # 问一句「要 await 吗」：MCP 工具要，本地工具不要
                result = await result
        except Exception as exc:                   # 兜底：绝不让异常抛穿循环
            return f"错误：{tool.name} 执行失败（{type(exc).__name__}: {exc}）"
        return result if isinstance(result, str) else str(result)
