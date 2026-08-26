"""Run a read-only Fusion API script through the MCP tunnel and print its output.

  python3 fx.py <script.py>        # the file must define run(_context)
  python3 fx.py -                  # read the script from stdin
NEVER saves the document: everything here is measurement, and the user's CAD file is theirs.
"""
import json, sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import fusion_mcp as F

src = sys.stdin.read() if sys.argv[1] == '-' else open(sys.argv[1], encoding='utf-8').read()
F.connect()
out = F.call('fusion_mcp_execute', {'featureType': 'script', 'object': {'script': src}})
if 'error' in out:
    print('ERROR', json.dumps(out['error'], ensure_ascii=False)[:3000]); sys.exit(1)
for c in out['result'].get('content', []):
    t = c.get('text', '')
    try:                       # the adapter wraps script stdout in {"message": ...}
        j = json.loads(t)
        t = j.get('message', t) if isinstance(j, dict) else t
    except Exception:
        pass
    print(t)
if out['result'].get('isError'):
    sys.exit(2)
