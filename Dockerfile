FROM node:24.4.1-alpine3.22 AS web
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.mjs ./
COPY public ./public
COPY .openai ./.openai
COPY src ./src
COPY scripts ./scripts
COPY worker ./worker
COPY tests ./tests
RUN npm run build

FROM python:3.12.11-slim-bookworm
LABEL org.opencontainers.image.title="Egresscope" \
      org.opencontainers.image.description="Multi-user mihomo gateway console and traffic attribution service" \
      org.opencontainers.image.source="https://github.com/Rhythmicc/Egresscope" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EGRESSCOPE_STATIC_DIR=/app/static \
    EGRESSCOPE_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
COPY server ./server
COPY --from=web /src/dist/client ./static
RUN useradd --system --uid 10001 --create-home egresscope && mkdir -p /data && chown -R egresscope:egresscope /data
USER egresscope
EXPOSE 2086
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2086/health/ready', timeout=3)"
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "2086", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
