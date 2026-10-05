# Web front + agent + MCP server in one Cloud Run container (docs/deploy-web.md).
# The agent starts the MCP server as a stdio subprocess, so there is one service and one URL.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first, so code changes reuse this layer.
COPY apps/agent/pyproject.toml apps/agent/uv.lock apps/agent/
COPY apps/mcp-server/pyproject.toml apps/mcp-server/uv.lock apps/mcp-server/
RUN uv sync --project apps/agent --frozen --no-dev --no-install-project \
 && uv sync --project apps/mcp-server --frozen --no-dev --no-install-project

COPY apps/agent apps/agent
COPY apps/mcp-server apps/mcp-server
COPY evals/cases/results evals/cases/results
RUN uv sync --project apps/agent --frozen --no-dev \
 && uv sync --project apps/mcp-server --frozen --no-dev

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

ENV MCP_SERVER_COMMAND=/app/apps/mcp-server/.venv/bin/bank-mcp PORT=8080
EXPOSE 8080
CMD ["/app/apps/agent/.venv/bin/bank-web"]
