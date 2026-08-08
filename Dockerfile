# Among-I Server Handler — Docker container
#
# Build:
#   docker build -t amongi-server .
#
# Run (minimal):
#   docker run -d --name amongi-server \
#     -v $(pwd)/engine/firebase-key.json:/app/engine/firebase-key.json:ro \
#     -v amongi-logs:/app/log \
#     amongi-server
#
# Run with render relay + Tailscale funnel:
#   docker run -d --name amongi-server \
#     -v $(pwd)/engine/firebase-key.json:/app/engine/firebase-key.json:ro \
#     -v amongi-logs:/app/log \
#     -p 8081:8081 \
#     amongi-server --render --funnel

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Among-I Server Handler"
LABEL org.opencontainers.image.description="Runs Among-I experiments from a Firestore job queue"

# ── System dependencies ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Tailscale (optional, for funnel support) ────────────────────────
# One-liner install; fails gracefully if Tailscale isn't needed at runtime.
RUN curl -fsSL https://tailscale.com/install.sh | sh || true

# ── Python dependencies ──────────────────────────────────────────────
WORKDIR /app/engine

COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application ───────────────────────────────────────────────────────
# Copy the engine directory (self-contained — all imports resolve within)
COPY engine/ .

# ── Volumes ───────────────────────────────────────────────────────────
# Log output (mounted at /app/log so --log-dir /app/log works)
RUN mkdir -p /app/log
VOLUME ["/app/log"]

# firebase-key.json should be bind-mounted:
#   -v $(pwd)/engine/firebase-key.json:/app/engine/firebase-key.json:ro

# ── Runtime ───────────────────────────────────────────────────────────
EXPOSE 8081

ENV PYTHONUNBUFFERED=1

# Default entrypoint: server handler. All args are forwarded.
# Override with: docker run ... amongi-server --name my-server --render
ENTRYPOINT ["python", "server_handler.py"]
CMD []
