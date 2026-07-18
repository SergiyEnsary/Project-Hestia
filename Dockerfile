# syntax=docker/dockerfile:1

FROM node:22-alpine AS pythia-build
WORKDIR /build/pythia
COPY hestia/interfaces/pythia/package.json hestia/interfaces/pythia/package-lock.json ./
RUN npm ci
COPY hestia/interfaces/pythia/ ./
RUN npm run typecheck && npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HESTIA_CONFIG=/run/hestia/config.yaml

RUN groupadd --gid 10001 hestia \
    && useradd --uid 10001 --gid hestia --no-create-home --home-dir /nonexistent hestia \
    && mkdir -p /var/lib/hestia \
    && chown 10001:10001 /var/lib/hestia

WORKDIR /app
COPY pyproject.toml README.md ./
COPY hestia/ ./hestia/
COPY --from=pythia-build /build/pythia/dist/ ./hestia/interfaces/pythia/dist/
RUN pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["hestia", "serve"]
