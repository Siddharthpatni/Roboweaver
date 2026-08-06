FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /build/wheels .

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system roboweaver && useradd --system --gid roboweaver --create-home roboweaver
COPY --from=builder /build/wheels /tmp/wheels
RUN python -m pip install --no-index --find-links=/tmp/wheels roboweaver \
    && python -m pip check \
    && rm -rf /tmp/wheels

USER roboweaver
WORKDIR /home/roboweaver
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=2)" || exit 1

CMD ["roboweaver", "dashboard", "--host", "0.0.0.0", "--port", "8080", "--no-self-heal"]
