import ast
from pathlib import Path


def _visit(node, prefix, file, functions, raw_calls):
    """Ek tree ke andar classes aur functions dhundhta hai."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _visit(child, f"{prefix}.{child.name}", file, functions, raw_calls)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{prefix}.{child.name}"
            functions[qname] = file
            for sub in ast.walk(child):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    if isinstance(f, ast.Name):
                        raw_calls.append((qname, f.id))
                    elif isinstance(f, ast.Attribute):
                        raw_calls.append((qname, f.attr))


def parse_repo(root):
    """Returns (functions, edges). Code ko chalata nahi, sirf padhta hai."""
    root = Path(root)
    functions = {}
    raw_calls = []
    for path in root.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        _visit(tree, module, str(path.relative_to(root)), functions, raw_calls)

    by_simple = {}
    for q in functions:
        by_simple.setdefault(q.split(".")[-1], []).append(q)

    edges = set()
    for caller, name in raw_calls:
        for target in by_simple.get(name, []):
            if target != caller:
                edges.add((caller, target))
    return functions, sorted(edges)


if __name__ == "__main__":
    import sys
    funcs, edges = parse_repo(sys.argv[1])
    print(len(funcs), "functions,", len(edges), "calls")
    for a, b in edges:
        print(a, "->", b)
