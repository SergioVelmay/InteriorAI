# syntax=docker/dockerfile:1
# Contexto de build: raíz del repo (necesita uv.lock y shared/).

FROM ghcr.io/astral-sh/uv:0.13 AS uv

# --- builder: resuelve dependencias desde uv.lock --------------------------------
FROM python:3.14-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Capa de dependencias (solo se invalida si cambia el lock o algún pyproject)
COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml shared/
COPY backend/pyproject.toml backend/
COPY frontend/pyproject.toml frontend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package interiorai-frontend --no-install-workspace

# Código propio, instalado como paquete (no editable)
COPY shared/ shared/
COPY frontend/ frontend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package interiorai-frontend --no-editable

# --- runtime: solo el venv, usuario sin privilegios -------------------------------
FROM python:3.14-slim AS runtime
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid app --no-create-home app \
    && mkdir -p /app/data /tmp/gradio && chown app:app /tmp/gradio
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    GRADIO_TEMP_DIR=/tmp/gradio
WORKDIR /app
# Falla el build si falta alguna dependencia
RUN python -c "import ui.app"
USER app

EXPOSE 7860
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('FRONTEND_PORT', '7860')}/\", timeout=4)"]

CMD ["python", "-m", "ui"]
