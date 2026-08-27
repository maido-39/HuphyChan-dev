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

# Hard ceiling on how many values any script may request per response. The measured host
# ceiling is 98304 floats (524288 B); requests beyond it do not fail cleanly - a burst of
# over-limit responses wedged the script host TWICE on 2026-08-27, and recovery needs a
# person at the CAD PC. 65536 = 2/3 of measured, clamped here so no caller can exceed it
# by convention-breaking; run_script refuses rather than truncates.
SLICE_VALUES_MAX = 65536

URL = os.environ.get('FUSION_MCP', 'http://127.0.0.1:27182/mcp')
_session = {'id': None, 'n': 0}


def _post(payload, notify=False):
    """One JSON-RPC call. `notify` sends a notification (no id) - the spec requires the
    initialized notification to carry NO id, and this server rejects the session until it
    arrives, so getting that distinction right is what completes the handshake."""
    _session['n'] += 1
    payload = dict(payload, jsonrpc='2.0')
    if not notify:
        payload['id'] = _session['n']
    hdr = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    if _session['id']:
        hdr['Mcp-Session-Id'] = _session['id']
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=hdr)
    with urllib.request.urlopen(req, timeout=180) as r:
        sid = r.headers.get('Mcp-Session-Id') or r.headers.get('mcp-session-id')
        if sid:
            _session['id'] = sid
        body = r.read().decode()
        ctype = r.headers.get('Content-Type', '')
    if notify:
        return {}
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
    _post({'method': 'notifications/initialized', 'params': {}}, notify=True)
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


# The connector silently does NOT execute a script source above 4 KiB and still answers
# {"success": true, "message": ""} - measured 2026-08-23: 3777 B ran, 4289 B did not. Refuse
# anything near that rather than let an edit vanish without a trace.
SCRIPT_MAX = 3800


def _guard(src, what):
    if len(src.encode()) > SCRIPT_MAX:
        raise ValueError(f'{what}: script is {len(src.encode())} B, above the connector\'s '
                         f'~4 KiB limit - it would be silently skipped. Split the work.')


class HostWedged(RuntimeError):
    """The connector's script host is dead - it fails BEFORE the submitted source runs.

    Signature: every `fusion_mcp_execute` (even an empty script, even one that is not valid
    Python) comes back as a `RecursionError` raised inside a `__getattr__` at line 25 of the
    connector's own `<string>` wrapper, while `fusion_mcp_read` keeps answering normally.
    Nothing sent over the wire can clear it: the Fusion MCP add-in has to be restarted on
    the CAD PC (Utilities -> Add-Ins -> Scripts and Add-Ins -> stop, then start).

    Retrying is worse than useless here - a caller that loops over 30 bodies burns five
    round trips and twelve seconds each to relearn the same fact, and ends up with a
    half-finished result. Raise this on the first sighting and let the caller stop.
    """


def _wedged(txt):
    return 'RecursionError' in txt and 'in __getattr__' in txt


def host_alive():
    """True when the script host executes submitted source. One cheap round trip.

    Answers the only question worth asking before a long fetch, and distinguishes the two
    ways the tunnel disappoints: `fusion_mcp_read` answering while every script dies is the
    wedge above; a `URLError`/`RemoteDisconnected` is the ssh forward, not the add-in.
    """
    r = call('fusion_mcp_execute', {'featureType': 'script',
                                    'object': {'script': 'def run(_c):\n    print("PONG")\n'}})
    if isinstance(r, dict) and _wedged(str(r.get('error', ''))):
        return False
    return 'PONG' in (r.get('message', '') if isinstance(r, dict) else str(r))


def assert_slice_ok(count):
    if count > SLICE_VALUES_MAX:
        raise ValueError(f'slice of {count} values exceeds SLICE_VALUES_MAX={SLICE_VALUES_MAX}; '
                         'over-limit requests wedge the Fusion script host (2026-08-27 x2)')


def script(src, tries=4):
    """Run a Fusion script and get its payload back.

    The connector's stdout capture returns an empty message (Fusion build here), but the
    ERROR path hands back the whole traceback - so a script signals its result by raising
    with the JSON as the exception text. `src` must define `emit(obj)`-free code that ends
    in `raise Payload(json.dumps(...))`; the helper below wraps that for you.

    Raises HostWedged immediately - without retrying - when the script host is the thing
    that is broken, because no number of tries changes that answer.
    """
    import time
    wrapper = ('import json\nclass _P(Exception):\n    pass\n'
               'def emit(o):\n    raise _P("JSONSTART" + json.dumps(o))\n' + src)
    _guard(wrapper, 'script')
    last = ''
    for k in range(tries):
        r = call('fusion_mcp_execute', {'featureType': 'script', 'object': {'script': wrapper}})
        txt = r.get('error', '') if isinstance(r, dict) else str(r)
        last = txt
        if _wedged(txt):
            raise HostWedged(
                'Fusion script host is wedged - it dies before the submitted script runs '
                '(fusion_mcp_read still answers). Restart the Fusion MCP add-in on the CAD '
                'PC, then re-run. Nothing here can fix it remotely.')
        if 'JSONSTART' in txt:
            body = txt.split('JSONSTART', 1)[1]
            # the traceback ends the exception text at the final newline
            body = body.rsplit('\n', 1)[0] if body.endswith('\n') else body
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
        time.sleep(0.5 + k)
    raise RuntimeError(f'no payload after {tries} tries:\n{last}')


def printed(src):
    """Run a Fusion script and return whatever it print()ed, as a string.

    The other half of `script()`: on the connector build behind the tunnel now, stdout IS
    captured and handed back as {"message": ...}. It is the wider of the two channels for
    bulk data (`upper_meshes_fusion.py --probe` measures both), and unlike the exception
    channel it does not have a traceback wrapped around the payload. Returns '' when the
    script printed nothing; raises on a script error, HostWedged on the wedge.
    """
    _guard(src, 'printed')
    r = call('fusion_mcp_execute', {'featureType': 'script', 'object': {'script': src}})
    if not isinstance(r, dict):
        return str(r)
    err = str(r.get('error', ''))
    if _wedged(err):
        raise HostWedged(
            'Fusion script host is wedged - it dies before the submitted script runs '
            '(fusion_mcp_read still answers). Restart the Fusion MCP add-in on the CAD PC.')
    if err:
        raise RuntimeError(err[:2000])
    return r.get('message', '')


def run_script(src):
    """Run a Fusion script for its SIDE EFFECT and let it end normally.

    `script()` gets its payload back by raising, and Fusion rolls the document edit back
    when the script ends in an exception - so anything that CHANGES the design has to
    return quietly and be verified by a separate read.
    """
    _guard(src, 'run_script')
    r = call('fusion_mcp_execute', {'featureType': 'script', 'object': {'script': src}})
    if isinstance(r, dict) and not r.get('success', False):
        raise RuntimeError(r.get('error', r))
    return r
