import re
import sys
from pathlib import Path

repo = sys.argv[1] if len(sys.argv) > 1 else "../demo_repos/requests"
p = Path(repo) / "src/requests/sessions.py"
s = p.read_text()
if re.search(r"def prepare_request\([^)]*strict_mode", s):
    print("Demo change already applied. Run: scripts/demo.sh reset")
    sys.exit(0)
new = re.sub(r"(def prepare_request\(self, request)([^)]*)\)", r"\1\2, strict_mode)", s, count=1)
if new == s:
    print("Could not find prepare_request signature")
else:
    p.write_text(new)
    print("Demo change applied: prepare_request now requires strict_mode")
