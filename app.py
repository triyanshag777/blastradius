from pathlib import Path

from falkordb import FalkorDB
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import agent
import report
import tools

app = FastAPI()


class Q(BaseModel):
    question: str


def short(name):
    return ".".join(name.split(".")[-2:])


def last_result(results, tool, key):
    for r in reversed(results):
        if r["tool"] == tool and isinstance(r["result"], dict) and key in r["result"]:
            return r["result"]
    return None


def build_graph(results):
    imp = last_result(results, "impact", "dependents")
    if not imp:
        return None
    target = imp["target"]
    deps = [d for d in imp["dependents"] if d["hops"] <= 3][:60]
    tst = last_result(results, "tests_for", "tests")
    tests = (tst["tests"] if tst else [])[:4]

    hops, kind = {target: 0}, {target: "target"}
    for d in deps:
        hops[d["function"]] = d["hops"]
        kind[d["function"]] = "fn"
    for t in tests:
        hops[t["test"]] = t["hops"]
        kind[t["test"]] = "test"
    names = list(hops)

    g = FalkorDB(host="localhost", port=6379).select_graph("blastradius")
    rows = g.query(
        "MATCH (a:Function)-[:CALLS]->(b:Function) "
        "WHERE a.name IN $n AND b.name IN $n RETURN a.name, b.name",
        {"n": names},
    ).result_set

    path = None
    if deps:
        far = max(deps, key=lambda d: d["hops"])
        path = tools.explain_path(far["function"], target).get("path")

    return {
        "target": target,
        "nodes": [{"id": n, "label": short(n), "hops": hops[n], "kind": kind[n]} for n in names],
        "edges": [{"source": a, "target": b} for a, b in rows],
        "path": path,
        "total_dependents": imp["total_dependents"],
        "shown": len(deps),
    }


@app.post("/api/ask")
async def api_ask(q: Q):
    answer, calls, results = await agent.ask(q.question)
    return {
        "answer": answer,
        "calls": [{"tool": n, "args": a} for n, a in calls],
        "graph": build_graph(results),
    }


class T(BaseModel):
    target: str


@app.post("/api/pr_comment")
def api_pr_comment(t: T):
    return {"markdown": report.make_pr_comment(t.target)}


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("index.html").read_text()
