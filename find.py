import sys
from falkordb import FalkorDB

g = FalkorDB(host="localhost", port=6379).select_graph("blastradius")
rows = g.query(
    "MATCH (f:Function) WHERE f.name CONTAINS $s AND f.is_test = false "
    "RETURN f.name LIMIT 15",
    {"s": sys.argv[1]},
).result_set
for (n,) in rows:
    print(n)
