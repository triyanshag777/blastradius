import sys
from falkordb import FalkorDB


def experts(name, limit=3, graph_name="blastradius"):
    g = FalkorDB(host="localhost", port=6379).select_graph(graph_name)
    q = (
        "MATCH (p:Person)-[e:EDITED]->(f:Function {name: $name}) "
        "RETURN p.name AS person, e.commits AS commits "
        "ORDER BY commits DESC LIMIT $limit"
    )
    return g.query(q, {"name": name, "limit": limit}).result_set


if __name__ == "__main__":
    rows = experts(sys.argv[1])
    if not rows:
        print("Koi author nahi mila (file commit hui hai?)")
    for person, commits in rows:
        print(f"{person}: {commits} commit(s)")
