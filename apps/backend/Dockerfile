# C360 backend (FastAPI + uv). Free UBI minimal base from the Red Hat public
# registry (no login / subscription needed).
FROM registry.access.redhat.com/ubi9/python-312-minimal:latest

# The image's default user is non-root (UID 1001) and owns /opt/app-root.
WORKDIR /opt/app-root/src

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/app-root/src/.venv/bin:${PATH}"

# uv is only needed at build time (the base image ships an app-root virtualenv).
RUN pip install --no-cache-dir uv

# Dependencies first for layer caching: pinned by uv.lock.
COPY --chown=1001:0 pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=1001:0 . .

USER 1001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# No --reload in the container. Port 8000 is only published on the compose
# network (never on the host), so binding all container interfaces is required
# for the nginx sidecar to reach it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
