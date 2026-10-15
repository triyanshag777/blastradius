import sys
from falkordb import FalkorDB


def tests_for(name, max_hops=5, graph_name="blastradius"):
    g = FalkorDB(host="localhost", port=6379).select_graph(graph_name)
    q = (
        f"MATCH p = (t:Function)-[:CALLS*1..{int(max_hops)}]->(f:Function {{name: $name}}) "
        "WHERE t.is_test = true "
        "RETURN t.name AS test, min(length(p)) AS hops "
        "ORDER BY hops, test"
    )
    return g.query(q, {"name": name}).result_set


if __name__ == "__main__":
    rows = tests_for(sys.argv[1])
    if not rows:
        print("Is function ko koi test cover nahi karta (ya naam galat hai)")
    for t, hops in rows:
        print(f"{hops} hop(s): {t}")
