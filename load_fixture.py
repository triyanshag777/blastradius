import json
import sys

from falkordb import FalkorDB


def load(path, graph_name="blastradius"):
    data = json.load(open(path))
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph(graph_name)
    try:
        g.delete()
    except Exception:
        pass
    g = db.select_graph(graph_name)

    g.query("CREATE INDEX FOR (f:Function) ON (f.name)")
    g.query(
        "UNWIND $rows AS r CREATE (:Function {name: r.name, file: r.file, is_test: r.is_test, in_tests: r.in_tests})",
        {"rows": data["functions"]},
    )
    g.query(
        "UNWIND $rows AS r MATCH (a:Function {name: r.a}), (b:Function {name: r.b}) CREATE (a)-[:CALLS]->(b)",
        {"rows": [{"a": a, "b": b} for a, b in data["edges"]]},
    )

    rows = []
    for fn in data["functions"]:
        for person, n in data["authors"].get(fn["file"], {}).items():
            rows.append({"fn": fn["name"], "p": person, "n": n})
    if rows:
        g.query(
            "UNWIND $rows AS r MATCH (f:Function {name: r.fn}) "
            "MERGE (p:Person {name: r.p}) CREATE (p)-[:EDITED {commits: r.n}]->(f)",
            {"rows": rows},
        )
    print(f"Loaded {len(data['functions'])} functions, {len(data['edges'])} calls, {len(rows)} author links from {path}")


if __name__ == "__main__":
    load(sys.argv[1])
