import sys
from falkordb import FalkorDB

g = FalkorDB(host="localhost", port=6379).select_graph("blastradius")
rows = g.query(
    "MATCH (a:Function {name: $a}), (b:Function {name: $b}) "
    "WITH shortestPath((a)-[:CALLS*..6]->(b)) AS p "
    "RETURN [n IN nodes(p) | n.name]",
    {"a": sys.argv[1], "b": sys.argv[2]},
).result_set
if not rows or not rows[0][0]:
    print("Koi rasta nahi mila")
else:
    print("\n  -> ".join(rows[0][0]))
