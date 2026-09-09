#!/usr/bin/env python3
"""벤치 카메라를 네트워크로 내보낸다. **로봇 위에서 돌린다.**

2026-09-09, 사용자: "실험 셋업을 볼수있는 카메라를 달아두었는데, 네트워크로 압축해서
스트리밍 하고, 모터 움직이는거 보면서 실험해 봐."

두 가지를 동시에 내보낸다. 보는 쪽이 사람과 기계로 나뉘기 때문이다.

* ``/stream.mjpg`` — 사람이 브라우저로 본다. 계속 흐르는 그림.
* ``/snapshot.jpg`` — 실험 스크립트가 한 장씩 집어 간다. 흐르는 영상은 프로그램이 "지금
  이 순간"을 집어내기 어렵고, 실험은 **특정 시각의 한 장**이 필요하다.

압축을 다시 하지 않는다
-----------------------
이 카메라는 MJPEG 를 **직접** 내보낸다(3840x2160 까지). 그래서 받아서 그대로 흘리면 되고,
로봇의 4개짜리 가상 CPU 로 재압축할 일이 없다. 실험 중에 CPU 를 카메라가 먹으면 제어 주기가
흔들리는데, 지금 재려는 것이 바로 그 시간이라 특히 곤란하다.

카메라는 한 프로그램만 열 수 있다
---------------------------------
그래서 카메라를 여는 곳은 여기 한 군데뿐이다. 촬영은 ``gst-launch-1.0`` 이 하고 최근 몇 장을
메모리 디스크에 떨궈 두며, 이 서버는 그 파일을 읽어 두 경로로 나눠 준다. 실험 스크립트가
카메라를 직접 열려고 하면 서로 막는다.

    # 로봇 위에서
    python3 cam_server.py --width 1280 --height 720 --fps 15 --port 8099

    # 보는 쪽
    http://10.8.0.14:8099/            브라우저
    curl -s http://10.8.0.14:8099/snapshot.jpg -o now.jpg
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FRAME_DIR = "/dev/shm/pygcam"
"""메모리 디스크에 쓴다. 초당 15장을 SD 카드에 쓰면 카드가 상하고, 어차피 최근 것 말고는
쓸 데가 없다."""

KEEP_FILES = 4
"""남겨 두는 장수. 읽는 쪽이 파일을 여는 순간 쓰는 쪽이 지우면 반쪽짜리를 읽는다 — 몇 장
여유를 두고 **가장 최근이 아니라 두 번째로 최근** 것을 읽어 그 경합을 피한다."""


class Camera:
  def __init__(self, device: str, width: int, height: int, fps: int):
    self.device, self.width, self.height, self.fps = device, width, height, fps
    self.proc: subprocess.Popen | None = None

  def start(self) -> None:
    shutil.rmtree(FRAME_DIR, ignore_errors=True)
    os.makedirs(FRAME_DIR, exist_ok=True)
    pipeline = [
      "gst-launch-1.0", "-q",
      "v4l2src", f"device={self.device}", "!",
      f"image/jpeg,width={self.width},height={self.height},framerate={self.fps}/1", "!",
      "multifilesink", f"location={FRAME_DIR}/f%06d.jpg",
      f"max-files={KEEP_FILES}", "post-messages=false",
    ]
    self.proc = subprocess.Popen(pipeline, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    if self.proc.poll() is not None:
      err = (self.proc.stderr.read() or "")[:600]
      raise RuntimeError(f"카메라를 열지 못했습니다:\n{err}")

  def latest(self) -> bytes | None:
    """가장 최근이 아니라 **그 다음 것**을 읽는다 - 위 KEEP_FILES 주석의 이유."""
    files = sorted(glob.glob(f"{FRAME_DIR}/f*.jpg"))
    for path in reversed(files[:-1] if len(files) > 1 else files):
      try:
        with open(path, "rb") as f:
          data = f.read()
        # JPEG 는 FFD8 로 시작해 FFD9 로 끝난다. 쓰는 중인 파일은 끝이 없다.
        if data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9":
          return data
      except OSError:
        continue
    return None

  def stop(self) -> None:
    if self.proc and self.proc.poll() is None:
      self.proc.send_signal(signal.SIGINT)
      try:
        self.proc.wait(timeout=3)
      except subprocess.TimeoutExpired:
        self.proc.kill()


CAM: Camera | None = None

PAGE = """<!doctype html><meta charset=utf-8><title>bench camera</title>
<style>body{background:#111;color:#ddd;font:13px system-ui;margin:0;padding:12px}
img{max-width:100%;border:1px solid #333;border-radius:4px}</style>
<h3 style="margin:0 0 8px">벤치 카메라</h3>
<img src="/stream.mjpg" alt="stream">
<p>한 장만: <a style="color:#7bf" href="/snapshot.jpg">/snapshot.jpg</a></p>
"""


class Handler(BaseHTTPRequestHandler):
  protocol_version = "HTTP/1.1"

  def log_message(self, *a):  # 조용히 - 실험 로그에 섞이면 읽기 어렵다
    pass

  def do_GET(self):
    if self.path.startswith("/snapshot"):
      data = CAM.latest()
      if data is None:
        self.send_error(503, "no frame yet")
        return
      self.send_response(200)
      self.send_header("Content-Type", "image/jpeg")
      self.send_header("Content-Length", str(len(data)))
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      self.wfile.write(data)
      return
    if self.path.startswith("/stream"):
      self.send_response(200)
      self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
      self.send_header("Cache-Control", "no-store")
      self.end_headers()
      last = None
      try:
        while True:
          data = CAM.latest()
          if data is not None and data != last:
            last = data
            self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n"
                             + f"Content-Length: {len(data)}\r\n\r\n".encode() + data + b"\r\n")
            self.wfile.flush()
          time.sleep(0.02)
      except (BrokenPipeError, ConnectionResetError):
        return
    body = PAGE.encode()
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)


def main(argv=None) -> int:
  global CAM
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--device", default="/dev/video0")
  ap.add_argument("--width", type=int, default=1280)
  ap.add_argument("--height", type=int, default=720)
  ap.add_argument("--fps", type=int, default=15)
  ap.add_argument("--port", type=int, default=8099)
  a = ap.parse_args(argv)

  CAM = Camera(a.device, a.width, a.height, a.fps)
  try:
    CAM.start()
  except RuntimeError as e:
    print(e, file=sys.stderr)
    return 1
  n = 0
  for _ in range(40):
    if CAM.latest():
      n = 1
      break
    time.sleep(0.25)
  print(f"카메라 {a.device} {a.width}x{a.height} {a.fps}fps · 첫 장 "
        f"{'받음' if n else '아직 없음'}", flush=True)
  srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
  srv.daemon_threads = True
  print(f"http://10.8.0.14:{a.port}/  (브라우저)   /snapshot.jpg (한 장)", flush=True)
  t = threading.Thread(target=srv.serve_forever, daemon=True)
  t.start()
  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    pass
  finally:
    srv.shutdown()
    CAM.stop()
    print("카메라 껐습니다")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
