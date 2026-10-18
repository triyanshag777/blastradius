import ast
import difflib
import os
import re
import subprocess
import time
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

import tools
from parser import COMMON

load_dotenv()
FENCE = "`" * 3


def short(n):
    return ".".join(n.split(".")[-2:])


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def read_version(repo, ref, path):
    if ref is None:
        p = Path(repo) / path
        return p.read_text(errors="replace") if p.exists() else ""
    code, out = git(repo, "show", f"{ref}:{path}")
    return out if code == 0 else ""


def changed_files(repo, base, head):
    args = ["diff", "--name-only", base] + ([head] if head else [])
    code, out = git(repo, *args)
    if code != 0:
        raise RuntimeError("git diff failed. Is this a git repository with at least one commit?")
    return [l for l in out.splitlines() if l.endswith(".py")]


def module_of(path):
    return Path(path).with_suffix("").as_posix().replace("/", ".")


def collect(tree, module):
    funcs = {}

    def visit(node, prefix, in_class):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}.{child.name}", True)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[f"{prefix}.{child.name}"] = (child, in_class)

    visit(tree, module, False)
    return funcs


def body_fp(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(ast.dump(n) for n in body)


def args_fp(fn):
    return ast.dump(fn.args)


def sig_text(fn):
    return ast.unparse(fn.args)


def is_static(fn):
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)


def compat(fn, call, bound):
    """Returns None if the call fits the signature, else a short problem text."""
    a = fn.args
    pos = [p.arg for p in a.posonlyargs + a.args]
    n_posonly = len(a.posonlyargs)
    if bound and pos:
        pos = pos[1:]
        n_posonly = max(0, n_posonly - 1)
    n_def = len(a.defaults)
    required_pos = pos[: max(0, len(pos) - n_def)]
    kwonly = [k.arg for k in a.kwonlyargs]
    required_kw = [k.arg for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]

    if any(isinstance(x, ast.Starred) for x in call.args):
        return None
    if any(k.arg is None for k in call.keywords):
        return None

    n = len(call.args)
    if n > len(pos) and not a.vararg:
        return f"too many positional arguments ({n} given, {len(pos)} accepted)"
    given = set(pos[:n])
    for k in call.keywords:
        if k.arg in given:
            return f"got multiple values for '{k.arg}'"
        if k.arg in pos[n_posonly:] or k.arg in kwonly:
            given.add(k.arg)
        elif a.kwarg is None:
            return f"unexpected keyword argument '{k.arg}'"
    missing = [p for p in required_pos if p not in given] + [k for k in required_kw if k not in given]
    if missing:
        return "missing required argument(s): " + ", ".join(f"'{m}'" for m in missing)
    return None


def callee_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id, "name"
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name) and f.value.id in ("self", "cls"):
            return f.attr, "self"
        return f.attr, "attr"
    return None, None


def call_sites(caller_fn, simple, target_in_class):
    out = []
    for node in ast.walk(caller_fn):
        if not isinstance(node, ast.Call):
            continue
        name, kind = callee_name(node)
        if name != simple:
            continue
        if kind == "attr" and name in COMMON:
            continue
        if target_in_class and kind == "name":
            continue
        if not target_in_class and kind == "self":
            continue
        out.append(node)
    return out


def direct_callers(name):
    rows = tools._g().query(
        "MATCH (c:Function)-[:CALLS]->(f:Function {name: $n}) RETURN c.name, c.file", {"n": name}
    ).result_set
    return [(r[0], r[1]) for r in rows]


def same_name_count(simple):
    rows = tools._g().query(
        "MATCH (f:Function) WHERE f.name CONTAINS $s AND f.in_tests = false RETURN f.name",
        {"s": "." + simple},
    ).result_set
    return sum(1 for (n,) in rows if n.split(".")[-1] == simple)


def offsets(src, node):
    lines = src.split("\n")

    def to_abs(lineno, col):
        before = sum(len(l) + 1 for l in lines[: lineno - 1])
        return before + len(lines[lineno - 1].encode()[:col].decode(errors="ignore"))

    return to_abs(node.lineno, node.col_offset), to_abs(node.end_lineno, node.end_col_offset)


def verify(new_text, fn, bound, expected_name):
    try:
        e = ast.parse(new_text.strip(), mode="eval").body
    except SyntaxError:
        return False
    if not isinstance(e, ast.Call):
        return False
    name, _ = callee_name(e)
    return name == expected_name and compat(fn, e, bound) is None


def rule_fix(fn, call, bound, text, simple):
    a = fn.args
    pos = [p.arg for p in a.posonlyargs + a.args]
    if bound and pos:
        pos = pos[1:]
    n_def = len(a.defaults)
    required_pos = pos[: max(0, len(pos) - n_def)]
    required_kw = [k.arg for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]
    given = set(pos[: len(call.args)]) | {k.arg for k in call.keywords}
    missing = [p for p in required_pos + required_kw if p not in given]
    if not missing or not text.rstrip().endswith(")"):
        return None
    inner = text.rstrip()[:-1].rstrip()
    if inner.endswith(","):
        inner = inner[:-1]
    sep = "" if inner.endswith("(") else ", "
    return inner + sep + ", ".join(f"{m}=None" for m in missing) + ")"


def llm_fix(client, model, old_sig, new_sig, name, caller, call_text, problem):
    prompt = (
        "A Python function signature changed and this call no longer matches it.\n"
        f"Old signature: ({old_sig})\nNew signature: ({new_sig})\n"
        f"Function being called: {name}\nProblem: {problem}\n"
        f"Broken call (inside {caller}):\n{call_text}\n\n"
        "Return ONLY the corrected call expression, in the same style, with no explanation and no code fences. "
        "If a new required parameter needs a value you cannot know, pass None for it as a placeholder (the developer will choose the real value). "
        "Change nothing else."
    )
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], temperature=0
    )
    text = (resp.choices[0].message.content or "").strip()
    text = re.sub(rf"^{FENCE}\w*\s*|\s*{FENCE}$", "", text).strip().strip("`").strip()
    return text


def make_finding(severity, kind, target_full, target_label, caller, file, line, call_text, message, fix=None, edit=None):
    return {
        "severity": severity, "type": kind, "target_full": target_full, "target": target_label,
        "caller": caller, "caller_short": short(caller) if "." in caller else caller,
        "file": file, "line": line, "call_text": call_text, "message": message,
        "fix": fix, "_edit": edit,
    }


def check(repo, base="HEAD", head=None, use_llm=True):
    files = changed_files(repo, base, head)
    base_funcs, head_funcs, src_cache, findings = {}, {}, {}, []

    def source(path):
        if path not in src_cache:
            src_cache[path] = read_version(repo, head, path)
        return src_cache[path]

    def funcs_of(path):
        try:
            return collect(ast.parse(source(path)), module_of(path))
        except SyntaxError:
            return {}

    for path in files:
        module = module_of(path)
        bsrc, hsrc = read_version(repo, base, path), source(path)
        try:
            btree = ast.parse(bsrc) if bsrc else None
        except SyntaxError:
            btree = None
        try:
            htree = ast.parse(hsrc) if hsrc else None
        except SyntaxError as e:
            if btree is not None:
                findings.append(make_finding(
                    "error", "syntax", path, path, path, path, e.lineno or 0, "",
                    f"SyntaxError in this file after your change: {e.msg} (line {e.lineno})"))
            continue
        if btree is not None:
            for q, (fn, cls) in collect(btree, module).items():
                base_funcs[q] = (fn, cls, path)
        if htree is not None:
            for q, (fn, cls) in collect(htree, module).items():
                head_funcs[q] = (fn, cls, path)

    removed = {q: v for q, v in base_funcs.items() if q not in head_funcs}
    added = {q: v for q, v in head_funcs.items() if q not in base_funcs}
    by_fp = {}
    for q, (fn, cls, p) in added.items():
        by_fp.setdefault((body_fp(fn), args_fp(fn)), []).append(q)

    changes = []
    for q, (fn, cls, p) in removed.items():
        c = by_fp.get((body_fp(fn), args_fp(fn)), [])
        if len(c) == 1 and body_fp(fn):
            changes.append({"name": q, "kind": "renamed", "new_name": c[0], "detail": f"renamed to {short(c[0])}"})
        else:
            changes.append({"name": q, "kind": "removed", "new_name": None, "detail": "removed"})
    for q, (hfn, hcls, p) in head_funcs.items():
        if q in base_funcs:
            bfn = base_funcs[q][0]
            if args_fp(bfn) != args_fp(hfn):
                changes.append({"name": q, "kind": "signature", "new_name": None,
                                "detail": f"({sig_text(bfn)}) -> ({sig_text(hfn)})"})
            elif body_fp(bfn) != body_fp(hfn):
                changes.append({"name": q, "kind": "body", "new_name": None, "detail": "logic changed"})

    pending, seen = [], set()
    for ch in changes:
        q, kind = ch["name"], ch["kind"]
        if kind == "body":
            continue
        simple = q.split(".")[-1]
        bfn, bcls, _ = base_funcs[q]
        bound = bcls and not is_static(bfn)
        hfn = head_funcs[q][0] if kind == "signature" else None
        new_q = ch["new_name"]
        n_same = same_name_count(simple)
        sev = "error" if n_same <= 1 else "warning"

        for caller, cfile in direct_callers(q):
            if caller == q:
                continue
            cfn = funcs_of(cfile).get(caller)
            if cfn is None:
                continue
            for node in call_sites(cfn[0], simple, bcls):
                start, end = offsets(source(cfile), node)
                text = source(cfile)[start:end]
                key = (cfile, start, end)
                if key in seen:
                    continue
                edit = [cfile, start, end]
                label = short(q)
                if kind == "signature":
                    problem = compat(hfn, node, bound)
                    if not problem or compat(bfn, node, bound):
                        continue
                    seen.add(key)
                    f = make_finding(sev, "signature", q, label, caller, cfile, node.lineno, text,
                                     f"{problem}. `{label}` now takes ({sig_text(hfn)}).", None, edit)
                    findings.append(f)
                    rf = rule_fix(hfn, node, bound, text, simple)
                    if rf and verify(rf, hfn, bound, simple):
                        f["fix"] = {"old": text, "new": rf, "verified": True, "source": "rule"}
                    else:
                        pending.append((f, hfn, bound, sig_text(bfn), sig_text(hfn), simple, problem))
                elif kind == "removed":
                    seen.add(key)
                    findings.append(make_finding(
                        sev, "removed", q, label, caller, cfile, node.lineno, text,
                        f"`{label}` was removed, but this code still calls it.", None, edit))
                else:
                    seen.add(key)
                    new_simple = new_q.split(".")[-1]
                    new_text = text.replace(simple, new_simple, 1)
                    new_fn, new_cls, _ = head_funcs[new_q]
                    ok = verify(new_text, new_fn, new_cls and not is_static(new_fn), new_simple)
                    findings.append(make_finding(
                        "error", "renamed", q, label, caller, cfile, node.lineno, text,
                        f"`{label}` was renamed to `{short(new_q)}`, but this call still uses the old name.",
                        {"old": text, "new": new_text, "verified": ok, "source": "rule"}, edit))

    client, model = None, os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    if use_llm and os.getenv("LLM_API_KEY") and pending:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ["LLM_BASE_URL"], max_retries=6)
    pending.sort(key=lambda p: ".tests." in p[0]["caller"] or p[0]["caller"].startswith("tests."))
    done = 0
    for f, hfn, bound, osig, nsig, simple, problem in pending:
        if client is None or done >= 10:
            break
        try:
            new_text = llm_fix(client, model, osig, nsig, simple, f["caller_short"], f["call_text"], problem)
        except Exception:
            continue
        done += 1
        time.sleep(2)
        f["fix"] = {"old": f["call_text"], "new": new_text,
                    "verified": verify(new_text, hfn, bound, simple), "source": "ai"}

    tests_all = set()
    for ch in changes:
        imp, tst = tools.impact(ch["name"]), tools.tests_for(ch["name"])
        ch["short"] = short(ch["name"])
        ch["dependents"] = imp["total_dependents"]
        ch["tests"] = tst["total_tests"]
        tests_all.update(t["test"] for t in tst["tests"])
    names = sorted({t.split(".")[-1] for t in tests_all})[:10]
    tests_cmd = 'pytest -k "' + " or ".join(names) + '"' if names else ""
    tests_total = max([len(tests_all)] + [c["tests"] for c in changes])

    edits = {}
    for f in findings:
        if f["fix"] and f["fix"]["verified"] and f["_edit"]:
            path, s, e = f["_edit"]
            edits.setdefault(path, []).append((s, e, f["fix"]["new"]))
    patch = ""
    for path, items in edits.items():
        src = source(path)
        new = src
        for s, e, t in sorted(set(items), reverse=True):
            new = new[:s] + t + new[e:]
        patch += "".join(difflib.unified_diff(
            src.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}"))
    if patch:
        Path("blastradius_fixes.patch").write_text(patch)

    counts = Counter(f["target_full"] for f in findings if f["type"] != "syntax")
    focus = counts.most_common(1)[0][0] if counts else None
    if focus is None:
        with_dep = [c for c in changes if c["dependents"] > 0]
        focus = max(with_dep, key=lambda c: c["dependents"])["name"] if with_dep else None

    return {"repo": repo, "changes": changes, "findings": findings, "tests_cmd": tests_cmd,
            "tests_total": tests_total, "patch": patch, "focus": focus}


def print_report(r):
    api = [c for c in r["changes"] if c["kind"] != "body"]
    logic = [c for c in r["changes"] if c["kind"] == "body"]
    print(f"\nChanged functions: {len(r['changes'])} ({len(api)} API change(s), {len(logic)} logic edit(s))")
    for c in api:
        print(f"  - [{c['kind']}] {c['short']}: {c['detail']}  ({c['dependents']} dependents, {c['tests']} tests)")
    if logic:
        print(f"  + {len(logic)} function(s) with logic edits (cannot be checked statically, see the tests below)")
    errs = [f for f in r["findings"] if f["severity"] == "error"]
    warns = [f for f in r["findings"] if f["severity"] == "warning"]
    print(f"\nNew problems caused by your change: {len(errs)} definite, {len(warns)} possible")
    for f in r["findings"]:
        print(f"\n[{f['severity'].upper()}] {f['caller_short']}  ({f['file']}:{f['line']})")
        print("  " + f["message"])
        if f["call_text"]:
            print("  - " + f["call_text"])
        if f["fix"]:
            tag = "verified" if f["fix"]["verified"] else "NOT verified"
            print(f"  + {f['fix']['new']}   ({f['fix']['source']}, {tag})")
    if r["tests_cmd"]:
        print(f"\nTests to run ({r['tests_total']} reach your change):\n  {r['tests_cmd']}")
    if r["patch"]:
        print("\nSuggested patch saved to blastradius_fixes.patch")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--head", default=None)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--fail-on-error", action="store_true")
    a = ap.parse_args()
    res = check(a.repo, a.base, a.head, use_llm=not a.no_llm)
    if not res["changes"]:
        print("No changed Python functions found. Edit a function (without committing) and run again.")
    else:
        print_report(res)
    if a.fail_on_error and any(f["severity"] == "error" for f in res["findings"]):
        sys.exit(1)
