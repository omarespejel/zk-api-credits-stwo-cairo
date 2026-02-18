#!/usr/bin/env python3

import gzip, json, sys

if len(sys.argv) != 2:
    print("usage: scripts/proof_size.py path/to/proof.json", file=sys.stderr)
    raise SystemExit(2)

p = sys.argv[1]
raw = open(p, "rb").read()
obj = json.loads(raw)

minified = json.dumps(obj, separators=(",", ":")).encode("utf-8")
gz = gzip.compress(raw)

print("pretty/minified/gzip bytes:", len(raw), len(minified), len(gz))
