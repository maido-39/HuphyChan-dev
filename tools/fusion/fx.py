"""Run a read-only Fusion API script through the MCP tunnel and print its output.

    python3 tools/fusion/fx.py <script.py>     # file must define run(_context)
    python3 tools/fusion/fx.py -               # script on stdin

Why this exists alongside mcp_client.script(): that helper returns its payload by RAISING,
because on the connector build of 2026-08-23 stdout was not captured. On the build now behind
the tunnel (Fusion 2704.1.53) plain print() IS returned, wrapped as {"message": ...}. This
takes the simple path; mcp_client.script() remains correct if the capture regresses.

NEVER saves the document - measurement only.
"""
import json
import sys

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

src = sys.stdin.read() if sys.argv[1] == '-' else open(sys.argv[1], encoding='utf-8').read()
M.connect()
# mcp_client.call already unwraps the JSON-RPC envelope, so what comes back is the
# connector's own {"message": <script stdout>, "success": bool} (or {"error": ...}).
out = M.call('fusion_mcp_execute', {'featureType': 'script', 'object': {'script': src}})
if not isinstance(out, dict):
    print(out)
    sys.exit(0)
if out.get('error'):
    print('ERROR', json.dumps(out['error'], ensure_ascii=False)[:4000])
    sys.exit(1)
print(out.get('message', json.dumps(out, ensure_ascii=False)[:4000]), end='')
sys.exit(0 if out.get('success', True) else 2)
