FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

# Installs the mycel framework (the diplomat/connector/orchestrator entrypoints).
# Node configs and data are NOT used from the image — the demo mounts them from
# the scaffolded directory; company deployments supply their own.
RUN pip install --no-cache-dir .

EXPOSE 8000

# default entrypoint is the agent node; the reference connector overrides this
# with `command: ["connector"]`
CMD ["diplomat"]
