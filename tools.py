from falkordb import FalkorDB

GRAPH = "blastradius"


def _g():
    return FalkorDB(host="localhost", port=6379).select_graph(GRAPH)


def find_function(text, limit=10):
    rows = _g().query(
        "MATCH (f:Function) WHERE f.name CONTAINS $s AND f.in_tests = false "
        "RETURN f.name LIMIT $limit",
        {"s": text, "limit": int(limit)},
    ).result_set
    return {"matches": [r[0] for r in rows]}


def impact(name, max_hops=5):
    q = (
        f"MATCH p = (d:Function)-[:CALLS*1..{int(max_hops)}]->(f:Function {{name: $name}}) "
        "WHERE d.in_tests = false AND d.name <> $name "
        "RETURN d.name AS dependent, min(length(p)) AS hops "
        "ORDER BY hops, dependent"
    )
    rows = _g().query(q, {"name": name}).result_set
    return {
        "target": name,
        "total_dependents": len(rows),
        "dependents": [{"function": r[0], "hops": r[1]} for r in rows[:40]],
    }


def tests_for(name, max_hops=5):
    q = (
        f"MATCH p = (t:Function)-[:CALLS*1..{int(max_hops)}]->(f:Function {{name: $name}}) "
        "WHERE t.is_test = true "
        "RETURN t.name AS test, min(length(p)) AS hops "
        "ORDER BY hops, test"
    )
    rows = _g().query(q, {"name": name}).result_set
    return {
        "target": name,
        "total_tests": len(rows),
        "tests": [{"test": r[0], "hops": r[1]} for r in rows[:40]],
    }


def experts(name, limit=3):
    rows = _g().query(
        "MATCH (p:Person)-[e:EDITED]->(f:Function {name: $name}) "
        "RETURN p.name AS person, e.commits AS commits "
        "ORDER BY commits DESC LIMIT $limit",
        {"name": name, "limit": int(limit)},
    ).result_set
    return {"target": name, "experts": [{"person": r[0], "commits": r[1]} for r in rows]}


def explain_path(source, target):
    rows = _g().query(
        "MATCH (a:Function {name: $a}), (b:Function {name: $b}) "
        "WITH shortestPath((a)-[:CALLS*..6]->(b)) AS p "
        "RETURN [n IN nodes(p) | n.name]",
        {"a": source, "b": target},
    ).result_set
    if not rows or not rows[0][0]:
        return {"source": source, "target": target, "path": None}
    return {"source": source, "target": target, "path": rows[0][0]}


def criticality(limit=10):
    rows = _g().query(
        "CALL algo.pageRank('Function', 'CALLS') YIELD node, score "
        "WITH node, score WHERE node.in_tests = false "
        "RETURN node.name AS name, score ORDER BY score DESC LIMIT $limit",
        {"limit": int(limit)},
    ).result_set
    return {"most_critical": [{"function": r[0], "score": round(r[1], 4)} for r in rows]}


def criticality_of(name):
    rows = _g().query(
        "CALL algo.pageRank('Function', 'CALLS') YIELD node, score "
        "WITH node, score WHERE node.in_tests = false "
        "RETURN node.name AS name, score ORDER BY score DESC"
    ).result_set
    names = [r[0] for r in rows]
    if name not in names:
        return None
    rank = names.index(name) + 1
    return {
        "rank": rank,
        "of": len(names),
        "percentile": round(100 * rank / len(names), 1),
        "score": round(rows[rank - 1][1], 4),
    }


def node_info(name):
    g = _g()
    meta = g.query("MATCH (f:Function {name: $n}) RETURN f.file, f.is_test", {"n": name}).result_set
    if not meta:
        return None
    q_in = "MATCH (c:Function)-[:CALLS]->(f:Function {name: $n}) WHERE c.in_tests = false RETURN c.name ORDER BY c.name"
    q_out = "MATCH (f:Function {name: $n})-[:CALLS]->(c:Function) RETURN c.name ORDER BY c.name"
    callers = [r[0] for r in g.query(q_in, {"n": name}).result_set]
    callees = [r[0] for r in g.query(q_out, {"n": name}).result_set]
    return {
        "name": name,
        "file": meta[0][0],
        "is_test": bool(meta[0][1]),
        "callers": {"count": len(callers), "sample": callers[:6]},
        "calls": {"count": len(callees), "sample": callees[:6]},
        "tests": tests_for(name)["total_tests"],
        "experts": experts(name)["experts"],
        "criticality": criticality_of(name),
    }


QUERIES = {
    "find_function": """MATCH (f:Function)
WHERE f.name CONTAINS $s AND f.in_tests = false
RETURN f.name LIMIT 10""",
    "impact (multi-hop traversal, up to 5 hops)": """MATCH p = (d:Function)-[:CALLS*1..5]->(f:Function {name: $name})
WHERE d.in_tests = false AND d.name <> $name
RETURN d.name AS dependent, min(length(p)) AS hops
ORDER BY hops, dependent""",
    "tests_for": """MATCH p = (t:Function)-[:CALLS*1..5]->(f:Function {name: $name})
WHERE t.is_test = true
RETURN t.name AS test, min(length(p)) AS hops
ORDER BY hops, test""",
    "experts": """MATCH (p:Person)-[e:EDITED]->(f:Function {name: $name})
RETURN p.name AS person, e.commits AS commits
ORDER BY commits DESC LIMIT 3""",
    "explain_path (shortest path)": """MATCH (a:Function {name: $a}), (b:Function {name: $b})
WITH shortestPath((a)-[:CALLS*..6]->(b)) AS p
RETURN [n IN nodes(p) | n.name]""",
    "criticality (FalkorDB PageRank algorithm)": """CALL algo.pageRank('Function', 'CALLS') YIELD node, score
WITH node, score WHERE node.in_tests = false
RETURN node.name AS name, score
ORDER BY score DESC LIMIT 10""",
}
