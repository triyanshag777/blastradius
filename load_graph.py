import sys
from falkordb import FalkorDB
from parser import parse_repo


def load(repo_path, graph_name="blastradius"):
    functions, edges = parse_repo(repo_path)
    db = FalkorDB(host="localhost", port=6379)
    g = db.select_graph(graph_name)

    try:
        g.delete()  # purana data saaf (agar graph pehle se hai)
    except Exception:
        pass
    g = db.select_graph(graph_name)

    g.query("CREATE INDEX FOR (f:Function) ON (f.name)")
    g.query(
        "UNWIND $rows AS r CREATE (:Function {name: r.name, file: r.file})",
        {"rows": [{"name": n, "file": f} for n, f in functions.items()]},
    )
    g.query(
        "UNWIND $rows AS r "
        "MATCH (a:Function {name: r.a}), (b:Function {name: r.b}) "
        "CREATE (a)-[:CALLS]->(b)",
        {"rows": [{"a": a, "b": b} for a, b in edges]},
    )
    print(f"Loaded {len(functions)} functions and {len(edges)} calls into '{graph_name}'")


if __name__ == "__main__":
    load(sys.argv[1])
