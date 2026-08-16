"""Assemble the whole campaign into one report: docs/fea_verdicts_current.md.

Pulls together what the separate stages produce, so the design decision can be read
in one place instead of five JSON files:

  envelope_P99.json  -> design stress and verdict at SF>1 / >1.5 / >2
  over_allowable     -> is a peak a numerical singularity or a real overloaded region
  lightweight.json   -> removable volume, and where material must be ADDED
  bolt_groups.json   -> separation / slip / shear margins of the screws themselves
  the *c variants    -> the motor-rigid-body bracket (with vs without the actuators)

Usage: report.py  (writes the file and prints it)
"""
import glob
import json
import os
import re

YIELD = 276.0
LEVELS = (1.0, 1.5, 2.0)
W = '/home/syaro/pyg_fea/work'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'docs', 'fea_verdicts_current.md')


def load(p):
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    specs = json.load(open(f'{HERE}/link_specs.json'))
    rev = re.search(r"ANALYSIS_REV = '([^']+)'",
                    open(f'{HERE}/run_link_env.py').read()).group(1)
    links = sorted(os.path.basename(os.path.dirname(f))
                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    rows = []
    for L in links:
        e = load(f'{W}/{L}/envelope_P99.json')
        lw = load(f'{W}/{L}/lightweight.json') or {}
        des = e.get('max_vM_design', e['max_vM'])
        oa = (e.get('over_allowable') or {}).get('SF>2.0', {})
        rows.append(dict(link=L, joint=e.get('joint'), rev=e.get('analysis_rev', '?'),
                         nodes=e.get('mesh_nodes'), raw=e['max_vM'], design=des,
                         SF=YIELD / des, over=oa.get('nodes_design'),
                         over_pct=oa.get('pct_design'), argmax=e.get('argmax_design',
                                                                    e.get('argmax_xyz')),
                         lw=lw.get('levels', {}), rein=lw.get('reinforce', {}),
                         total_cm3=lw.get('total_cm3'),
                         motors=specs.get(L, {}).get('actuators')))

    out = [f'# 링크 구조 판정 (현행) — 해석 리비전 `{rev}`', '',
           '`tools/fea/report.py`가 생성. 6061-T6 항복 276 MPa,',
           '허용 276 (SF>1) / 184 (SF>1.5) / 138 MPa (SF>2).', '',
           '설계 응력 = 하중 주입 절점과 구속 절점 근방을 **모두** 제외한 최대값.',
           '초과 절점 수는 특이점(절점 몇 개)과 실제 과부하(영역)를 가른다.', '',
           '| 링크 | 관절 | 노드 | raw MPa | **설계 MPa** | **SF** | SF>1 | SF>1.5 | SF>2 | SF>2 초과 | 최대점 |',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        v = {f'SF>{L}': ('PASS' if r['SF'] >= L else '**FAIL**') for L in LEVELS}
        ov = '—' if not r['over'] else f"{r['over']}개 ({r['over_pct']} %)"
        out.append(f"| {r['link']} | {r['joint']} | {r['nodes'] or '?'} | {r['raw']:.1f} | "
                   f"**{r['design']:.1f}** | **{r['SF']:.2f}** | {v['SF>1.0']} | {v['SF>1.5']} | "
                   f"{v['SF>2.0']} | {ov} | {r['argmax']} |")

    out += ['', '## 모터 강체 브래킷 (동일 렌치, 액추에이터 유/무)', '',
            '강체 하우징은 병렬 하중경로다. 유 = 응력 하한, 무 = 보수적 상한.', '',
            '| 링크 | 모터 포함 | 모터 제외 | 비 |', '|---|---|---|---|']
    for r in rows:
        if not r['link'].endswith('_nomotor'):
            continue
        base = r['link'].replace('c_', '_').replace('_nomotor', '')
        b = next((x for x in rows if x['link'].startswith(base.split('_')[0] + '_')
                  and not x['link'].endswith('_nomotor')), None)
        if b:
            out.append(f"| {base} | {b['design']:.1f} MPa (SF {b['SF']:.2f}) | "
                       f"{r['design']:.1f} MPa (SF {r['SF']:.2f}) | "
                       f"×{r['design'] / max(1e-9, b['design']):.2f} |")

    bg = load(f'{W}/bolt_groups.json') or {}
    if bg:
        out += ['', '## 체결부 (측정 렌치 하 볼트 그룹)', '',
                '| 체결면 | 볼트 | 인장/예압 | 분리여유 | 전단 (힘+비틀림) | 마찰여유 | 볼트전단 |',
                '|---|---|---|---|---|---|---|']
        seen = set()
        for k, v in bg.items():
            t = max(v['rows'], key=lambda x: x['T_N'])
            w = min(v['rows'], key=lambda x: x['slip_margin'])
            sig = (v['bolts'], t['size'], round(t['T_N']), round(w['V_N']))
            if sig in seen:
                continue
            seen.add(sig)
            flag = '**' if w['slip_margin'] < 1.0 else ''
            out.append(f"| {k.split(':')[0]} | {v['bolts']}×{t['size']} | "
                       f"{t['T_N']:.0f}/{t['preload_N']:.0f} N | {t['sep_margin']} | "
                       f"{w['V_N']:.0f} N ({w['V_force_N']:.0f}+{w['V_torsion_N']:.0f}) | "
                       f"{flag}{w['slip_margin']}{flag} | {w['shear_margin']} |")

    out += ['', '## 형상 최적화 (제거 가능 / 보강 필요)', '',
            '| 링크 | 총 체적 | SF>1.5 제거가능 | SF>2 제거가능 | SF>2 보강필요 |',
            '|---|---|---|---|---|']
    for r in rows:
        lw = r['lw']
        if not lw:
            continue
        rein = (r['rein'] or {}).get('SF>2.0', {})
        rtxt = ('—' if not rein.get('needed') else
                f"{rein['volume_cm3']} cm³, 두께 ×{rein['thickness_factor']}")
        out.append(f"| {r['link']} | {r['total_cm3'] or '—'} cm³ | "
                   f"{lw.get('SF>1.5', {}).get('removable_pct', '—')} % | "
                   f"{lw.get('SF>2.0', {}).get('removable_pct', '—')} % | {rtxt} |")

    out += ['', '## 케이스 설명', '']
    for r in rows:
        doc = (specs.get(r['link']) or {}).get('_doc')
        mot = specs.get(r['link'], {}).get('actuators')
        tag = ('액추에이터 없음' if mot == [] else
               ('액추에이터 %d개 강체' % len(mot)) if mot else '액추에이터 자동')
        out.append(f"- **{r['link']}** ({tag}) — {doc or '기본 케이스'}")

    txt = '\n'.join(out) + '\n'
    open(os.path.abspath(OUT), 'w').write(txt)
    print(txt)


if __name__ == '__main__':
    main()
