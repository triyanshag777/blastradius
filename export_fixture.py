import json
import sys

from parser import parse_repo
from load_graph import is_test_func, in_tests_file
from load_authors import file_authors


def export(repo, out):
    functions, edges = parse_repo(repo)
    funcs = [
        {"name": n, "file": f, "is_test": is_test_func(n, f), "in_tests": in_tests_file(f)}
        for n, f in functions.items()
    ]
    authors = {f: dict(file_authors(repo, f)) for f in sorted(set(functions.values()))}
    data = {"functions": funcs, "edges": [list(e) for e in edges], "authors": authors}
    with open(out, "w") as fh:
        json.dump(data, fh)
    print(f"Saved {len(funcs)} functions, {len(edges)} calls, {len(authors)} files to {out}")


if __name__ == "__main__":
    export(sys.argv[1], sys.argv[2])
