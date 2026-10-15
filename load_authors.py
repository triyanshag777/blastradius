import sys
import subprocess
from collections import Counter
from falkordb import FalkorDB


def file_authors(repo, file):
    out = subprocess.run(
        ["git", "-C", repo, "log", "--follow", "--format=%an", "--", file],
        capture_output=True, text=True,
    ).stdout
    return Counter(line.strip() for line in out.splitlines() if line.strip())


def load_authors(repo, graph_name="blastradius"):
    g = FalkorDB(host="localhost", port=6379).select_graph(graph_name)
    funcs = g.query("MATCH (f:Function) RETURN f.name, f.file").result_set

    cache, rows = {}, []
    for name, file in funcs:
        if file not in cache:
            cache[file] = file_authors(repo, file)
        for author, n in cache[file].items():
            rows.append({"fn": name, "p": author, "n": n})

    g.query("MATCH (p:Person) DETACH DELETE p")  # purana saaf
    if rows:
        g.query(
            "UNWIND $rows AS r "
            "MATCH (f:Function {name: r.fn}) "
            "MERGE (p:Person {name: r.p}) "
            "CREATE (p)-[:EDITED {commits: r.n}]->(f)",
            {"rows": rows},
        )
    print(f"Added {len(rows)} author links")


if __name__ == "__main__":
    load_authors(sys.argv[1])
