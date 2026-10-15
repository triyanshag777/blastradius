import sys
from pathlib import Path
from falkordb import FalkorDB
from parser import parse_repo


def is_test_func(qname, file):
    p = Path(file)
    in_test_file = "tests" in p.parts or p.name.startswith("test_") or p.name.endswith("_test.py")
    return in_test_file and qname.split(".")[-1].startswith("test")


def load(repo_path, graph_name="blastradius"):
    functions, edges = parse_repo(repo_path)
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph(graph_name)

    try:
        g.delete()  # purana data saaf
    except Exception:
        pass
    g = db.select_graph(graph_name)

    g.query("CREATE INDEX FOR (f:Function) ON (f.name)")
    rows = [
        {"name": n, "file": f, "is_test": is_test_func(n, f)}
        for n, f in functions.items()
    ]
    g.query(
        "UNWIND $rows AS r CREATE (:Function {name: r.name, file: r.file, is_test: r.is_test})",
        {"rows": rows},
    )
    g.query(
        "UNWIND $rows AS r "
        "MATCH (a:Function {name: r.a}), (b:Function {name: r.b}) "
        "CREATE (a)-[:CALLS]->(b)",
        {"rows": [{"a": a, "b": b} for a, b in edges]},
    )
    n_tests = sum(1 for r in rows if r["is_test"])
    print(f"Loaded {len(functions)} functions ({n_tests} tests) and {len(edges)} calls into '{graph_name}'")


if __name__ == "__main__":
    load(sys.argv[1])
