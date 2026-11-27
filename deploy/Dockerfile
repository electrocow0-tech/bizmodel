FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_COMPILE_BYTECODE=1 BIZMODEL_ROOT=/app PYTHONUNBUFFERED=1
WORKDIR /app
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app/src ./src
RUN uv sync --frozen --no-dev
CMD ["/venv/bin/uvicorn", "bizmodel.server:app", "--host", "0.0.0.0", "--port", "8000"]
