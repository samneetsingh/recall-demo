# The backend container for the Recall demo.
#
# Stage 1 uses Poetry to install the dependencies into a virtual environment.
# Stage 2 copies only that environment and the application code.

FROM python:3.13-slim AS builder

ENV POETRY_VERSION=2.3.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

# curl serves the container healthcheck. It is also useful to debug the
# container from the inside. The slim image does not have it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Run the process as a non-root user.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser app ./app

USER appuser

# Make port 8000 available on the container network. Docker Compose does not
# publish this port to the host.
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
