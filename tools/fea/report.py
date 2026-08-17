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

YIELD = 276.0          # the basis the user chose (typical 6061-T6)
YIELD_MIN = 240.0      # ASTM B221 MINIMUM specified for 6061-T6 - every SF above is 15 %
                       # more optimistic than a purchased-material guarantee
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
                         SF=YIELD / des, SF_min=YIELD_MIN / des,
                         p99=e.get('p99_vM'), over=oa.get('nodes_design'),
                         over_pct=oa.get('pct_design'), argmax=e.get('argmax_design',
                                                                    e.get('argmax_xyz')),
                         lw=lw.get('levels', {}), rein=lw.get('reinforce', {}),
                         total_cm3=lw.get('total_cm3'),
                         motors=specs.get(L, {}).get('actuators')))

    def kind(name):
        if name.endswith('_nomotor'):
            return '대조 (모터 제외)'
        if 'cornerfine' in name or name.endswith('_fine'):
            return '대조 (메시 수렴)'
        return '설계 판정'

    for r in rows:
        r['kind'] = kind(r['link'])
    rows.sort(key=lambda r: (r['kind'] != '설계 판정', r['link']))

    out = [f'# 링크 구조 판정 (현행) — 해석 리비전 `{rev}`', '',
           '`tools/fea/report.py`가 생성. 6061-T6 항복 276 MPa,',
           '허용 276 (SF>1) / 184 (SF>1.5) / 138 MPa (SF>2).', '',
           '> 276 MPa는 6061-T6의 **typical** 항복이다. ASTM B221 **최소보증치는 240 MPa**이므로 ',
           '> 구매 소재 보증 기준으로는 모든 SF가 **15 % 낮다**. 두 값을 병기한다.', '',
           '설계 응력 = 하중 주입 절점과 구속 절점 근방을 **모두** 제외한 최대값.',
           '초과 절점 수는 특이점(절점 몇 개)과 실제 과부하(영역)를 가른다.', '',
           '| 링크 | 성격 | 관절 | 노드 | raw MPa | **설계 MPa** | **SF (276)** | SF (240 최소보증) | p99 MPa | SF>1 | SF>1.5 | SF>2 | SF>2 초과 | 최대점 |',
           '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        v = {f'SF>{L}': ('PASS' if r['SF'] >= L else '**FAIL**') for L in LEVELS}
        ov = '—' if not r['over'] else f"{r['over']}개 ({r['over_pct']} %)"
        out.append(f"| {r['link']} | {r['kind']} | {r['joint']} | {r['nodes'] or '?'} | {r['raw']:.1f} | "
                   f"**{r['design']:.1f}** | **{r['SF']:.2f}** | {r['SF_min']:.2f} | "
                   f"{r['p99']:.1f} | {v['SF>1.0']} | {v['SF>1.5']} | "
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

    # one row per link with every tier the campaign now runs, so a reader does not have
    # to cross-reference four files to see whether a part is acceptable
    fat = (load(f'{W}/fatigue.json') or {}).get('links', {})
    asm = load(f'{W}/assembly_check.json') or {}
    out += ['', '## 티어 통합 (설계 P99 · 과부하 peak · 피로 · 조립)', '',
            '| 링크 | 설계 SF | peak SF | peak 항복초과 | 피로 SF@P99 | 피로 SF@RMS | 조립 판정 |',
            '|---|---|---|---|---|---|---|']
    for r in rows:
        if r['kind'] != '설계 판정':
            continue
        # a peak result from an older revision is worse than no number: L6 showed
        # peak SF 1.97 against a design SF of 0.65, which is impossible for a larger load
        pk = load(f"{W}/{r['link']}/envelope_peak.json")
        if pk and pk.get('analysis_rev') != rev:
            pk = None
        pkv = (YIELD / pk.get('max_vM_design', pk['max_vM'])) if pk else None
        pkn = (pk.get('over_allowable', {}).get('SF>1.0', {}).get('nodes_design')
               if pk else None)
        f = fat.get(r['link'], {})
        a = asm.get(r['link'], {}).get('verdict', '—')
        out.append(f"| {r['link']} | **{r['SF']:.2f}** | "
                   f"{('%.2f' % pkv) if pkv else '—'} | {pkn if pkn is not None else '—'} | "
                   f"{f.get('SF_fatigue_P99', '—')} | {f.get('SF_fatigue_RMS', '—')} | "
                   f"{a.split(':')[0]} |")
    out += ['', '> peak은 정적 사이징 기준이 아니라 **소성 미발생 확인**용이다(docs/62 §3c–4). ',
            '> 항복 초과 절점이 수천이면 국부가 아니라 형상 조치 대상이다.', '']

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
        # a failing part has no meaningful "removable" figure until it is reinforced
        def rem(level):
            if r['SF'] < level:
                return '판정 미달 — 보강 먼저'
            return f"{lw.get(f'SF>{level}', {}).get('removable_pct', '—')} %"
        out.append(f"| {r['link']} | {r['total_cm3'] or '—'} cm³ | {rem(1.5)} | "
                   f"{rem(2.0)} | {rtxt} |")

    out += ['',
            '> 제거 가능 체적은 **액추에이터 강체 포함** 모델(응력 하한)로 계산된 값이므로 '
            '절감의 **상한**으로 읽어야 한다. 보수적 경계(모터 제외)에서는 L5를 제외한 링크가 '
            '판정 자체를 통과하지 못하므로, 실제 절감량은 하우징 강성을 실제 값으로 모델링한 '
            '뒤에 확정된다.', '']
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
