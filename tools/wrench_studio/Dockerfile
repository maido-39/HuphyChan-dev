FROM python:3.11-slim
RUN pip install --no-cache-dir fastapi uvicorn numpy mujoco
WORKDIR /app
COPY server.py .
COPY static ./static
# mjlab data (npz/mjb/mesh) is volume-mounted read-only at runtime
ENV MJLAB_DIR=/mjlab
EXPOSE 8091
CMD ["python", "server.py"]
