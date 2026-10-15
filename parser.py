import ast
from pathlib import Path

# Ye naam dict/list/file ke methods mein bahut common hain.
# obj.get() jaisi calls ko hum Session.get se nahi jodte.
COMMON = {
    "get", "items", "keys", "values", "pop", "update", "append", "extend",
    "add", "remove", "copy", "join", "split", "strip", "startswith",
    "endswith", "format", "encode", "decode", "read", "write", "close",
    "lower", "upper", "replace", "setdefault", "clear", "index", "count",
    "sort", "find",
}


def _call_info(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id, "name"
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name) and f.value.id in ("self", "cls"):
            return f.attr, "self"
        return f.attr, "attr"
    return None, None


def _visit(node, prefix, file, functions, raw_calls):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            _visit(child, f"{prefix}.{child.name}", file, functions, raw_calls)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{prefix}.{child.name}"
            functions[qname] = file
            for sub in ast.walk(child):
                if isinstance(sub, ast.Call):
                    name, kind = _call_info(sub)
                    if name:
                        raw_calls.append((qname, name, kind))


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
    for caller, name, kind in raw_calls:
        if kind == "attr" and name in COMMON:
            continue
        candidates = by_simple.get(name, [])
        if kind in ("self", "name"):
            same_file = [t for t in candidates if functions[t] == functions[caller]]
            if kind == "self" or same_file:
                candidates = same_file
        for target in candidates:
            if target != caller:
                edges.add((caller, target))
    return functions, sorted(edges)


if __name__ == "__main__":
    import sys
    funcs, edges = parse_repo(sys.argv[1])
    print(len(funcs), "functions,", len(edges), "calls")
    for a, b in edges:
        print(a, "->", b)
