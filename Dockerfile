# ---------- build stage: resolve and install dependencies ----------
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./

# --no-dev keeps pytest, ruff and mypy out of the runtime image.
# --frozen fails the build when uv.lock does not match pyproject.toml.
RUN uv sync --frozen --no-dev --no-install-project


# ---------- runtime stage: only the app and its virtualenv ----------
FROM python:3.13-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv
COPY ./app ./app
COPY run.py ./

# Running as a non-root user: a container should not be able to modify its code.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /logs \
    && chown -R appuser:appuser /app /logs
USER appuser

EXPOSE 8000

# `python` resolves to the virtualenv, so nothing is installed at start-up.
CMD ["python", "run.py"]
