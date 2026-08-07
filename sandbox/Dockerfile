FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/roboweaver
RUN groupadd --gid 10001 sandbox && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent sandbox
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY scripts/research_sandbox_check.py ./scripts/research_sandbox_check.py
RUN pip install --no-cache-dir --no-deps . && pip install --no-cache-dir mujoco==3.11.0
USER sandbox
ENTRYPOINT ["python", "/opt/roboweaver/scripts/research_sandbox_check.py"]
