import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            print("Tools:", [t.name for t in listing.tools])
            res = await session.call_tool(
                "impact",
                {"name": "src.requests.sessions.Session.prepare_request", "max_hops": 2},
            )
            for block in res.content:
                print(block.text[:600])


asyncio.run(main())
