from falkordb import FalkorDB

GRAPH = "blastradius"


def _g():
    return FalkorDB(host="localhost", port=6379).select_graph(GRAPH)


def find_function(text, limit=10):
    rows = _g().query(
        "MATCH (f:Function) WHERE f.name CONTAINS $s AND f.is_test = false "
        "RETURN f.name LIMIT $limit",
        {"s": text, "limit": int(limit)},
    ).result_set
    return {"matches": [r[0] for r in rows]}


def impact(name, max_hops=5):
    q = (
        f"MATCH p = (d:Function)-[:CALLS*1..{int(max_hops)}]->(f:Function {{name: $name}}) "
        "WHERE d.is_test = false "
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
