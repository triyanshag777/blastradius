from pathlib import Path

from falkordb import FalkorDB
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import os

import agent
import check_change
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


def make_summary(target, total, tst):
    crit = tools.criticality_of(target)
    info = tools.node_info(target) or {}
    level = "LOW"
    if total >= 15 or (crit and crit["percentile"] <= 10):
        level = "HIGH"
    elif total >= 5:
        level = "MEDIUM"
    return {
        "risk": level,
        "dependents": total,
        "tests": tst["total_tests"] if tst else None,
        "direct_callers": (info.get("callers") or {}).get("count"),
        "criticality": crit,
    }


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
        "summary": make_summary(target, imp["total_dependents"], tst),
    }


@app.post("/api/ask")
async def api_ask(q: Q):
    try:
        answer, calls, results = await agent.ask(q.question)
    except Exception as e:
        return {"answer": "The AI service is busy or rate-limited (free tier). Wait about a minute and ask again.\n\nDetails: " + str(e)[:200], "calls": [], "graph": None}
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


REPO_PATH = os.environ.get("REPO_PATH", "../demo_repos/requests")


@app.post("/api/check")
def api_check():
    try:
        r = check_change.check(REPO_PATH, use_llm=True)
    except Exception as e:
        return {"error": f"Check failed: {e}"}
    graph = None
    if r["focus"]:
        results = [
            {"tool": "impact", "result": tools.impact(r["focus"])},
            {"tool": "tests_for", "result": tools.tests_for(r["focus"])},
        ]
        graph = build_graph(results)
        if graph:
            broken = {f["caller"] for f in r["findings"] if f["severity"] == "error"}
            for n in graph["nodes"]:
                if n["id"] in broken:
                    n["kind"] = "broken"
    r["graph"] = graph
    return r


@app.get("/api/node")
def api_node(name: str):
    return tools.node_info(name) or {"error": "function not found"}


@app.get("/api/why")
def api_why():
    import json
    p = Path("docs/compare_result.json")
    if not p.exists():
        return {"available": False}
    return {"available": True, **json.loads(p.read_text())}


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("index.html").read_text()
