# Wrench Studio — 서버/클라이언트 wrench 탐색기 (v4)
- 로컬: `cd mujoco-sim/mjlab && .venv/bin/python3 ../../tools/wrench_studio/server.py` → http://localhost:8091
- Docker: `cd tools/wrench_studio && docker compose up --build`
- API: /api/policies · /api/agg/{tag} · /api/blocks/{tag} · /api/motion/{tag}?start=&n=&ds= · /api/bodies/{tag} · /api/mesh/{stl}
- Wrench 부호: 반력×−1(브라켓 하중) 서버측 적용.
