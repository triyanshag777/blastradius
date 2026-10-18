import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import tools

load_dotenv()
TARGET = "src.requests.sessions.Session.prepare_request"
FILE = "../demo_repos/requests/src/requests/sessions.py"
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")


def short(n):
    return ".".join(n.split(".")[-2:])


def normalise(line):
    line = line.strip().strip("-*0123456789. ").replace("`", "")
    line = re.sub(r"\(.*$", "", line).strip()
    return short(line) if line and " " not in line else ""


graph = tools.impact(TARGET, 5)
graph_set = {short(d["function"]) for d in graph["dependents"]}

code = Path(FILE).read_text()
code = "\n".join(l for l in code.splitlines() if l.strip() and not l.strip().startswith("#"))

prompt = (
    "You are given ONE source file from a Python library (requests). "
    "List every function or method in the library that depends on Session.prepare_request, "
    "either by calling it directly or by calling something that calls it. "
    "Answer with one name per line in the form Class.method or module.function, and nothing else.\n\n"
    + code
)

client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"], max_retries=6)
resp = client.chat.completions.create(
    model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0
)
answer = resp.choices[0].message.content or ""
llm_set = {n for n in (normalise(l) for l in answer.splitlines()) if n}

found = graph_set & llm_set
missed = sorted(graph_set - llm_set)
extra = sorted(llm_set - graph_set)

print(f"\nGraph (BlastRadius) found {len(graph_set)} dependents.")
print(f"Plain LLM with one file found {len(found)} of them.")
print("\nMissed by the plain LLM:")
for m in missed:
    print("  -", m)
print("\nNames the LLM gave that are not in the graph result:")
for e in extra:
    print("  -", e)


import json as _json
from pathlib import Path as _Path
_Path("docs").mkdir(exist_ok=True)
_Path("docs/compare_result.json").write_text(_json.dumps({
    "target": short(TARGET),
    "graph_count": len(graph_set),
    "llm_found": len(found),
    "missed": missed,
    "extra": extra,
}))
