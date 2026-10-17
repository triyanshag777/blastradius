import re
import sys
from pathlib import Path

repo = sys.argv[1] if len(sys.argv) > 1 else "../demo_repos/requests"
p = Path(repo) / "src/requests/sessions.py"
s = p.read_text()
new = re.sub(r"(def prepare_request\(self, request)([^)]*)\)", r"\1\2, strict_mode)", s, count=1)
if new == s:
    print("Nothing changed (is the demo change already applied?)")
else:
    p.write_text(new)
    print("Demo change applied: prepare_request now requires strict_mode")
