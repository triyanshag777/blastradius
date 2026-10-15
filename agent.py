import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

SYSTEM = """You are BlastRadius, an assistant that analyzes the call graph of a Python repository.
Rules:
- Always use the tools. Never guess function names or results.
- If the user gives a partial function name, call find_function first and use the exact full name it returns.
- For 'what breaks if I change X' questions, call impact, tests_for and experts.
- For questions about the most critical or risky functions overall, call criticality.
- Answer briefly: dependents grouped by hops, tests to run, suggested reviewers.
- The graph comes from static analysis matched by function name, so mention that it can miss dynamic calls when relevant.
"""


async def ask(question, max_steps=8):
    client = AsyncOpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
    )
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    },
                }
                for t in mcp_tools
            ]

            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": question},
            ]
            calls, results = [], []
            for _ in range(max_steps):
                resp = await client.chat.completions.create(
                    model=MODEL, messages=messages, tools=tools, temperature=0
                )
                msg = resp.choices[0].message
                if not msg.tool_calls:
                    return msg.content, calls, results

                messages.append(msg.model_dump(exclude_none=True))
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments or "{}")
                    result = await session.call_tool(tc.function.name, args)
                    text = "".join(b.text for b in result.content if hasattr(b, "text"))
                    calls.append((tc.function.name, args))
                    try:
                        parsed = json.loads(text)
                    except Exception:
                        parsed = text
                    results.append({"tool": tc.function.name, "args": args, "result": parsed})
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": text}
                    )
            return "Agent stopped after too many steps.", calls, results


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    answer, calls, _ = asyncio.run(ask(question))
    print("\n=== Tools the agent chose ===")
    for name, args in calls:
        print(f"- {name}({args})")
    print("\n=== Answer ===")
    print(answer)
