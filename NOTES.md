# Decisions and findings

- Parser uses Python `ast` (code is never executed).
- Calls are matched by function name. Problem found on psf/requests: `os.environ.get()` was linked to `Session.get`, which created false paths.
- Fix: skip common dict/list/file method names, and match `self.x()` and plain `x()` calls inside the same file first. Edges dropped from 1754 to 1058 on requests.
- Authors come from `git log --follow` per file (file-level, not function-level).
- Known limits: dynamic dispatch, aliases, decorators, and other languages are not resolved.
