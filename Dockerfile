# Among-I Server Handler — Docker container
#
# Build (no local files needed — pulls the repo):
#   docker build -t amongi-server .
#
# Run (minimal):
#   docker run -d --name amongi-server \
#     -v $(pwd)/firebase-key.json:/app/engine/firebase-key.json:ro \
#     -v amongi-logs:/app/log \
#     amongi-server
#
# Run with render relay + Tailscale funnel:
#   docker run -d --name amongi-server \
#     -v $(pwd)/firebase-key.json:/app/engine/firebase-key.json:ro \
#     -v amongi-logs:/app/log \
#     -p 8081:8081 \
#     amongi-server --render --funnel

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Among-I Server Handler"
LABEL org.opencontainers.image.description="Runs Among-I experiments from a Firestore job queue"

# ── System dependencies ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# ── Tailscale (optional, for funnel support) ────────────────────────
RUN curl -fsSL https://tailscale.com/install.sh | sh || true

# ── Clone the repo ──────────────────────────────────────────────────
WORKDIR /app
RUN git clone https://github.com/rice-ai-alignment/AmongI .

# ── Python dependencies ──────────────────────────────────────────────
WORKDIR /app/engine
RUN pip install --no-cache-dir -r requirements.txt

# ── Volumes ───────────────────────────────────────────────────────────
RUN mkdir -p /app/log
VOLUME ["/app/log"]
# Mount your firebase-key.json at runtime:
#   -v $(pwd)/firebase-key.json:/app/engine/firebase-key.json:ro

# ── Runtime ───────────────────────────────────────────────────────────
EXPOSE 8081
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "server_handler.py"]
CMD []
