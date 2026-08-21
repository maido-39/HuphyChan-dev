"""Minimal MCP (streamable-HTTP) client for the Fusion 360 connector - no SDK, no session
registration needed: this session started before the server was registered, so the tools
are not in the harness; talking JSON-RPC to the endpoint directly is the workaround.

    python3 tools/fusion/mcp_client.py list                       # tool inventory
    python3 tools/fusion/mcp_client.py call <tool> '{"arg": 1}'   # one call, prints result
    FUSION_MCP=http://host:27182/mcp overrides the endpoint.
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get('FUSION_MCP', 'http://127.0.0.1:27182/mcp')
_session = {'id': None, 'n': 0}


def _post(payload):
    _session['n'] += 1
    payload = dict(payload, jsonrpc='2.0', id=_session['n'])
    hdr = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    if _session['id']:
        hdr['Mcp-Session-Id'] = _session['id']
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=hdr)
    with urllib.request.urlopen(req, timeout=120) as r:
        sid = r.headers.get('Mcp-Session-Id')
        if sid:
            _session['id'] = sid
        body = r.read().decode()
        ctype = r.headers.get('Content-Type', '')
    if 'text/event-stream' in ctype:
        # take the last JSON data line of the SSE stream
        msgs = [ln[5:].strip() for ln in body.splitlines() if ln.startswith('data:')]
        body = msgs[-1] if msgs else '{}'
    out = json.loads(body) if body.strip() else {}
    if 'error' in out:
        raise RuntimeError(out['error'])
    return out.get('result', out)


def connect():
    res = _post({'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'pygmalion-fusion-client', 'version': '0.1'}}})
    try:
        _post({'method': 'notifications/initialized', 'params': {}})
    except Exception:
        pass
    return res


def tools():
    return _post({'method': 'tools/list', 'params': {}}).get('tools', [])


def call(name, args=None):
    res = _post({'method': 'tools/call', 'params': {'name': name, 'arguments': args or {}}})
    parts = res.get('content', [])
    texts = [p.get('text', '') for p in parts if p.get('type') == 'text']
    txt = '\n'.join(texts)
    try:
        return json.loads(txt)
    except Exception:
        return txt


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'list'
    info = connect()
    print('server:', json.dumps(info.get('serverInfo', info))[:200])
    if cmd == 'list':
        for t in tools():
            print(f"- {t['name']}: {t.get('description', '')[:140]}")
            print('    args:', json.dumps(t.get('inputSchema', {}).get('properties', {}))[:300])
    elif cmd == 'call':
        print(json.dumps(call(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}),
                         ensure_ascii=False, indent=1)[:6000])
