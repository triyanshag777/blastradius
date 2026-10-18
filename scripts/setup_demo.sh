#!/bin/sh
# Clones psf/requests next to this repo at the pinned commit and loads the graph from the fixture.
set -e
COMMIT=$(cat fixtures/requests_commit.txt)
mkdir -p ../demo_repos
[ -d ../demo_repos/requests ] || git clone https://github.com/psf/requests.git ../demo_repos/requests
git -C ../demo_repos/requests checkout -q "$COMMIT"
python load_fixture.py fixtures/requests_graph.json
echo "Demo ready. Try: scripts/demo.sh break, then click 'Check my changes' in the dashboard."
