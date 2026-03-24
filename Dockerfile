FROM node:20-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=17320

WORKDIR /app

# Install Python and backend dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip curl \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /app/backend/requirements.txt

# Copy app code and static frontend
COPY backend /app/backend
COPY frontend/package.json /app/frontend/package.json
COPY frontend/package-lock.json /app/frontend/package-lock.json
RUN cd /app/frontend && npm ci --omit=dev
COPY frontend/public /app/frontend/public
COPY frontend/server.js /app/frontend/server.js
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

WORKDIR /app/backend

EXPOSE 17320 17321

# Health check every 30 seconds against backend health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:17321/api/health >/dev/null || exit 1

CMD ["bash", "/app/start.sh"]
