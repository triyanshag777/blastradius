from falkordb import FalkorDB

db = FalkorDB(host="localhost", port=6379)
g = db.select_graph("blastradius")
g.query("CREATE (:Function {name:'hello'})")
res = g.query("MATCH (f:Function) RETURN f.name")
print(res.result_set)
