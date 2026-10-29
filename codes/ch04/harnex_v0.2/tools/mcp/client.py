# harnex/tools/mcp/client.py —— 把 MCP server 的工具接进注册表
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tools import Tool


class McpServer:
    """启动一个 MCP server 子进程，把它的工具清单翻译成 Tool 注册进注册表。"""

    def __init__(self, command: str, args: list, scopes: list):
        self.command, self.args, self.scopes = command, args, scopes
        self._stack = AsyncExitStack()          # 记下要关的东西，退出时按相反顺序关掉

    async def attach(self, registry) -> None:
        # 第 1 步：拉起子进程。read / write 是两根管道，一根收它的输出，一根往里发指令
        params = StdioServerParameters(command=self.command, args=self.args)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()        # 握手：确认协议版本、交换各自能力

        # 第 2、3 步：问它有哪些工具，逐条翻译成 Tool
        for info in (await self._session.list_tools()).tools:
            registry.register(Tool(
                name=info.name,
                description=info.description,
                parameters=info.input_schema,      # MCP 给的 JSON Schema，直接可用
                handler=self._proxy(info.name),    # 执行那一栏换成「转发给它」
                scopes=self.scopes,                # 权限仍由本地决定，见下
            ))

    def _proxy(self, name: str):
        """给某个远程工具造一个本地执行函数：收下参数，转过去，再把结果转回来。"""
        async def call(args: dict) -> str:
            result = await self._session.call_tool(name, args)
            return "\n".join(part.text for part in result.content if part.type == "text")
        return call

    async def aclose(self) -> None:
        """关掉会话和子进程。由调用方在退出前调一次——不关就是留一个孤儿进程。"""
        await self._stack.aclose()


async def main():
    # 只有跑这个演示才需要这两样：装配线和主循环
    from build_registry import build_registry
    from loop.agent import run

    # 文件工具已搬进独立进程：本地不再装它们，否则 attach() 会撞上重名（4.1 的「重名拒」）
    registry = build_registry(exclude={"fs_read", "fs_write", "apply_patch"})
    fs = McpServer("python", ["-m", "tools.mcp.fs_server"], scopes=["fs:read", "fs:write"])
    await fs.attach(registry)                                     # 文件工具从独立进程接进来
    try:
        print(await run("帮我看看 harness 目录里有哪些文件", registry))
    finally:
        await fs.aclose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
