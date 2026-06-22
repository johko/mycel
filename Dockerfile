FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

# The version is derived from git by setuptools-scm, but the build context has
# no .git — so supply it explicitly. Defaults to a placeholder for local/dev
# image builds; pass the real version with `--build-arg MYCEL_VERSION=0.2.0`.
# (PyPI releases get their version from the tag via the release workflow, not here.)
ARG MYCEL_VERSION=0+docker
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${MYCEL_VERSION}

# Installs the mycel framework (the diplomat/connector/orchestrator entrypoints)
# plus the [demo] extra, so the reference RAG connector (qdrant + fastembed) runs
# from this same image. Node configs and data are NOT used from the image — the
# demo mounts them from the scaffolded directory; company deployments supply
# their own.
RUN pip install --no-cache-dir ".[demo]"

# Pre-warm the RAG connector's embedding model into the image so the archivists
# connector doesn't download ~50MB at first startup (which would outlast the
# node's connect retry budget). Cached at fastembed's default /tmp/fastembed_cache,
# which the connector reuses at runtime. Kept in sync with rag.py's _MODEL.
RUN python -c "from mycel.demo.connector.rag import _MODEL; from fastembed import TextEmbedding; TextEmbedding(_MODEL)"

EXPOSE 8000

# default entrypoint is the agent node; the reference connector overrides this
# with `command: ["connector"]`
CMD ["diplomat"]
