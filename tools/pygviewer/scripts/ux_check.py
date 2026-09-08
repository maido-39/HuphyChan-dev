#!/usr/bin/env python3
"""화면을 사람처럼 실제로 눌러보고, 눌러서 되는지 확인한다.

2026-09-08, 사용자 지적: "계속 너는 기능을 평면적으로만 개발하고, 실제 사용하는 과정을 전혀
고려하지 않고, UX 에서 테스트하지 않아."

맞는 지적이었다. 그때까지 확인이라고 한 것은 전부 **코드가 그렇게 쓰여 있는지**를 본 것이고,
그건 다음 세 가지를 하나도 못 잡는다. 실제로 잡힌 것만 적는다:

* **눌리지 않는 단추.** 조건이 안 맞으면 단추를 잠가 두었는데, 잠긴 단추는 눌러도 아무 사건도
  안 만든다. 이유는 화면에 잘 적혀 있었지만, 누른 사람에게는 완전한 무반응이었다.
* **누르는 도중에 사라지는 단추.** 상태 줄을 초당 몇 번씩 통째로 다시 그리고 있어서, 그 안의
  단추가 눌림과 떼임 사이에 교체된다. 이 검사가 36번 연속 실패하며 처음 드러났다.
* **글자는 있는데 손이 닿지 않는 곳에 있는 것.** 이유가 단추에서 일곱 줄 아래, 스크롤을
  내려야 보이는 자리에 있었다.

그래서 이 파일은 코드를 읽지 않는다. 도는 화면을 열어서 누르고, 눌린 결과를 확인한다.

    ux_check.py                 # 도는 뷰어(8095)를 검사
    ux_check.py --url http://...
    ux_check.py --keep-mode     # 끝나고 모드를 원래대로 안 돌려놓음

검사는 **아무것도 실물로 내보내지 않는다.** 무장(ARM)은 일부러 막힌 상태로만 눌러 본다 -
그게 이 검사가 확인하려는 것(막혔을 때 이유를 말하는가)이고, 실제로 무장되면 모터에 힘이
들어가기 때문이다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

DEFAULT_URL = "http://127.0.0.1:8095/static/dashboard.html"

SETTLE_MS = 4500
"""화면이 처음 붙고 상태를 한 바퀴 받아올 때까지. 이보다 짧으면 아직 안 그려진 것을 '없다'고
잘못 판정한다."""

ACT_MS = 1800
"""누른 뒤 결과를 볼 때까지. 모드 변경은 시뮬레이터 쪽 계산 주기를 한 번 기다려야 한다."""


class Checks:
  def __init__(self):
    self.rows: list[tuple[bool, str, str]] = []

  def add(self, ok: bool, name: str, detail: str = "") -> bool:
    self.rows.append((bool(ok), name, detail))
    return bool(ok)

  def report(self) -> int:
    bad = [r for r in self.rows if not r[0]]
    for ok, name, detail in self.rows:
      print(f"  {'PASS' if ok else 'FAIL'}  {name}")
      if detail:
        print(f"        {detail}")
    print(f"\n{len(self.rows) - len(bad)}/{len(self.rows)} 통과")
    return 1 if bad else 0


async def run(url: str, keep_mode: bool) -> int:
  from playwright.async_api import async_playwright

  c = Checks()
  async with async_playwright() as p:
    b = await p.chromium.launch()
    pg = await b.new_page(viewport={"width": 1500, "height": 1100})
    # 3D 창은 별도 프로그램(viser)이고 자기 오류를 낸다. 우리 화면의 오류만 세기 위해 끈다.
    await pg.goto(url + ("&" if "?" in url else "?") + "no3d=1", wait_until="load", timeout=30000)
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    await pg.wait_for_timeout(SETTLE_MS)

    async def state():
      return await pg.evaluate("""() => {
        const s = document.getElementById('mode-select');
        const st = (window.__pygdash && window.__pygdash.S.status) || {};
        const t = document.getElementById('toast');
        return {
          modeValue: s ? s.value : null,
          serverMode: st.mode || null,
          toast: t && t.style.display !== 'none' ? t.textContent.trim() : null,
        };
      }""")

    start = await state()
    original_mode = start["serverMode"]

    # ---------------------------------------------------------------- 모드를 바꿀 수 있는가
    c.add(start["modeValue"] is not None,
          "모드를 바꾸는 곳이 어느 탭에서나 보인다",
          f"현재 {start['serverMode']}")
    if start["modeValue"] is not None:
      want = "idle" if start["serverMode"] != "idle" else "manual"
      await pg.select_option("#mode-select", want)
      await pg.wait_for_timeout(ACT_MS)
      after = await state()
      c.add(after["serverMode"] == want,
            "고른 모드가 실제로 적용된다",
            f"{start['serverMode']} -> {after['serverMode']} (고른 값 {want})")

      # 서버가 반드시 거절하는 모드. 거절당한 뒤 화면이 거짓말을 하면 안 된다.
      await pg.select_option("#mode-select", "file_replay")
      await pg.wait_for_timeout(ACT_MS)
      ref = await state()
      c.add(ref["modeValue"] == ref["serverMode"],
            "거절당하면 화면이 실제 모드로 되돌아온다",
            f"화면 {ref['modeValue']} · 실제 {ref['serverMode']}")
      c.add(bool(ref["toast"]) and "409" in (ref["toast"] or ""),
            "거절 이유를 눈에 보이게 말한다",
            (ref["toast"] or "아무 말도 없었음")[:120])

    # ---------------------------------------------------------------- 막힌 단추가 답을 하는가
    await pg.get_by_text("Telemetry / Record", exact=False).first.click()
    await pg.wait_for_timeout(ACT_MS)
    # 반드시 막히는 상태로 만들어 둔다. 이 검사는 무장이 성공하면 안 된다.
    await pg.select_option("#mode-select", "idle")
    await pg.wait_for_timeout(ACT_MS)
    arm = pg.locator("#btn-tx-arm")
    c.add(await arm.count() > 0, "전송 켜기(ARM) 단추가 화면에 있다")
    if await arm.count():
      c.add(not await arm.is_disabled(),
            "막혀 있어도 눌리기는 한다",
            "잠긴 단추는 눌러도 아무 사건을 만들지 않아 완전한 무반응이 된다")
      await arm.scroll_into_view_if_needed()
      await arm.click()
      await pg.wait_for_timeout(900)
      st = await state()
      c.add(bool(st["toast"]) and "blocked" in (st["toast"] or "").lower(),
            "누르면 막힌 이유를 말한다",
            (st["toast"] or "아무 말도 없었음")[:140])
      fix = pg.locator("#btn-fix-mode")
      if await fix.count():
        # 여기서 30초를 기다리다 실패한 적이 있다. 다시 그려지며 사라지면 그게 곧 실패다.
        try:
          await fix.click(timeout=5000)
          await pg.wait_for_timeout(ACT_MS)
          fixed = await state()
          c.add(fixed["serverMode"] == "manual",
                "이유에 붙은 해결 단추가 실제로 고친다",
                f"모드 {fixed['serverMode']}")
        except Exception as e:
          c.add(False, "이유에 붙은 해결 단추가 눌린다",
                f"누르지 못했습니다 - 다시 그려지며 사라졌을 수 있습니다: {str(e)[:120]}")

    # ---------------------------------------------------------------- 시나리오를 눌러서 실행
    # 2026-09-08 사용자: "시나리오 하나하나 실행을 위한 버튼을 순서대로 눌러도 동작 제대로
    # 안한다." 그래서 여기서 확인하는 것은 "단추가 있다"가 아니라 **눌렀을 때 순서대로
    # 진행하고, 실물 앞에서 멈추고, 어디까지 갔는지 보인다**는 것이다.
    await pg.get_by_text("지금 무엇을 하는 중인가", exact=False).first.click()
    await pg.wait_for_timeout(ACT_MS)
    runbtn = pg.locator(".sc-run").first
    c.add(await runbtn.count() > 0, "시나리오마다 '실행' 단추가 있다")
    if await runbtn.count():
      # 실물로 나가지 않는 실행으로 확인한다. 이 검사가 모터를 돌리면 안 된다.
      started = await pg.evaluate("""async () => {
        // 화면이 고르는 것과 같은 목록에서 첫 호환 정책을 쓴다 - 검사가 화면과 다른 길로
        // 가면, 화면에서만 나는 문제를 못 잡는다.
        const list = await fetch('/policy/list').then(r => r.json());
        const pol = (list.policies || list || []).find(p => p.compatible);
        const r = await fetch('/scenario/run', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({key:'policy-drive', dry_run:true,
                                policy: pol ? pol.name : undefined})});
        return {status: r.status, body: (await r.text()).slice(0,200)};
      }""")
      c.add(started["status"] in (200, 409), "실행 요청이 받아들여지거나 이유를 말한다",
            f"{started['status']} {started['body'][:100]}")
      if started["status"] == 200:
        run = None
        for _ in range(30):
          await pg.wait_for_timeout(500)
          run = await pg.evaluate("() => fetch('/scenario/run').then(r=>r.json())")
          if run["state"] in ("waiting", "done", "failed"):
            break
        done = [s for s in (run["steps"] or []) if s["state"] == "done"]
        c.add(len(done) >= 5, "누르면 여러 단계가 순서대로 진행된다",
              f"{len(done)}단계 완료 · 상태 {run['state']}")
        c.add(run["state"] != "failed", "끝까지 가거나 사람을 기다린다",
              (run.get("message") or "")[:120])
        shown = await pg.evaluate("""() => {
          const b = document.getElementById('sc-run');
          return b ? b.textContent.trim().length : 0; }""")
        c.add(shown > 40, "어디까지 갔는지가 화면에 보인다", f"{shown}자")
        await pg.evaluate("() => fetch('/scenario/run/abort',{method:'POST'})")
        await pg.wait_for_timeout(ACT_MS)

    # ---------------------------------------------------------------- 손 없이 실물이 움직이지 않는가
    # 열쇠 감시는 boot 에서 한 번 걸리며 그 표시를 window 에 남긴다. 예전에는 Telemetry 탭을
    # 지은 뒤에야 걸렸고, 그래서 다른 탭에서 스페이스를 눌러도 서버는 아무것도 못 받았다 -
    # 실제 실행이 "스페이스를 누른 채 계속" 에서 멈춰 있길래 찾았다.
    hold = await pg.evaluate("() => !!window.__txKeyWired")
    c.add(bool(hold), "손을 놓았는지 보는 장치가 어느 탭에서나 걸려 있다",
          "예전에는 Telemetry 탭을 열어야만 걸렸고, 다른 탭에서는 스페이스가 무시됐다")

    # ---------------------------------------------------------------- 다시 그려도 안 사라지는가
    stable = await pg.evaluate("""async () => {
      const ids = ['tx-arm-block', 'tx-recover-note', 'tx-cfg-note'];
      const first = ids.map(i => document.getElementById(i));
      await new Promise(r => setTimeout(r, 1500));
      const second = ids.map(i => document.getElementById(i));
      // 같은 자리의 요소가 계속 같은 객체여야 한다. 매번 새로 만들면 그 안의 단추도 새것이다.
      return ids.map((id, k) => ({id, same: first[k] === second[k], exists: !!second[k]}));
    }""")
    for row in stable:
      if row["exists"]:
        c.add(row["same"], f"'{row['id']}' 줄이 계속 다시 만들어지지 않는다")

    c.add(not errs, "화면에서 오류가 나지 않는다", "; ".join(errs[:3]))

    if not keep_mode and original_mode:
      await pg.select_option("#mode-select", original_mode)
      await pg.wait_for_timeout(ACT_MS)
    await b.close()
  return c.report()


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--url", default=DEFAULT_URL)
  ap.add_argument("--keep-mode", action="store_true")
  a = ap.parse_args(argv)
  try:
    import playwright  # noqa: F401
  except ImportError:
    print("playwright 가 없습니다. mjlab 의 .venv 로 실행하세요.", file=sys.stderr)
    return 2
  print(f"화면을 실제로 눌러 봅니다: {a.url}\n")
  return asyncio.run(run(a.url, a.keep_mode))


if __name__ == "__main__":
  raise SystemExit(main())
