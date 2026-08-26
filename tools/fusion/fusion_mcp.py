"""Minimal MCP client for the Fusion 360 server reached over the SSH reverse tunnel.

The server runs on the Windows CAD box and is forwarded to 127.0.0.1:27182 here. It is not
registered as a Claude Code MCP server in this environment, so we speak the protocol directly:
initialize -> notifications/initialized -> tools/list | tools/call, reusing MCP-Session-Id.

  python3 fusion_mcp.py list
  python3 fusion_mcp.py call <tool> '<json args>'
"""
import json, sys, urllib.request

URL = "http://127.0.0.1:27182/mcp"
_sid = None


def _rpc(method, params=None, notify=False):
    global _sid
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = 1
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    if _sid:
        req.add_header("MCP-Session-Id", _sid)
    with urllib.request.urlopen(req, timeout=120) as r:
        _sid = r.headers.get("MCP-Session-Id") or _sid
        raw = r.read().decode()
    if not raw.strip():
        return None
    if raw.startswith("event:") or raw.startswith("data:"):        # SSE framing
        raw = "".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
    return json.loads(raw)


def connect():
    _rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "pygmalion", "version": "1"}})
    _rpc("notifications/initialized", {}, notify=True)


def list_tools():
    return _rpc("tools/list", {})


def call(name, args):
    return _rpc("tools/call", {"name": name, "arguments": args})


if __name__ == "__main__":
    connect()
    if sys.argv[1] == "list":
        r = list_tools()
        for t in r["result"]["tools"]:
            schema = t.get("inputSchema", {})
            props = list((schema.get("properties") or {}).keys())
            req = schema.get("required") or []
            print(f"- {t['name']}({', '.join(props)})  required={req}")
            print(f"    {(t.get('description') or '').strip().splitlines()[0][:160]}")
    else:
        out = call(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {})
        print(json.dumps(out, ensure_ascii=False, indent=1)[:8000])
