FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --upgrade pip build && python -m build --wheel

FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system roboweaver && useradd --system --gid roboweaver --create-home roboweaver
COPY --from=builder /build/dist/*.whl /tmp/
RUN python -m pip install /tmp/*.whl && rm /tmp/*.whl

USER roboweaver
WORKDIR /home/roboweaver
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2)" || exit 1

CMD ["roboweaver", "dashboard", "--host", "0.0.0.0", "--port", "8080", "--no-self-heal"]
