import sys
from falkordb import FalkorDB


def impact(name, max_hops=5, graph_name="blastradius"):
    g = FalkorDB(host="localhost", port=6379).select_graph(graph_name)
    q = (
        f"MATCH p = (d:Function)-[:CALLS*1..{int(max_hops)}]->(f:Function {{name: $name}}) "
        "WHERE d.is_test = false "
        "RETURN d.name AS dependent, min(length(p)) AS hops "
        "ORDER BY hops, dependent"
    )
    return g.query(q, {"name": name}).result_set


if __name__ == "__main__":
    rows = impact(sys.argv[1])
    if not rows:
        print("Koi dependent nahi mila (ya function ka naam galat hai)")
    for dep, hops in rows:
        print(f"{hops} hop(s) door: {dep}")
