FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=ap-south-1 \
    AWS_DEFAULT_REGION=ap-south-1 \
    JIRA_BASE_URL=https://bugdaddy.atlassian.net \
    JIRA_EMAIL=bugdaddy.in@gmail.com \
    JIRA_API_TOKEN=ATATT3xFfGF0GLKVzcRrbXOpgosSvhnZx_DIABorI6A-nkpUgB6eqR-a9kN2D3e6tND8nCTiLfGO0eeOzWoA4YvaeGPl1hY-syyT9EQwyeqjpRTYolh6tXuRAJ_QMxuwPrU4RIXPT5fxkUgzCNrYXynJiPMhV2pJFJxVPQe_VxNMW5f2YOjvuyE=2305F3DD \
    JIRA_PROJECT_KEY=BUG \
    JIRA_REVIEWER_ACCOUNT_ID=712020:db54222d-08dc-400b-9f00-4a812a18401c \
    JIRA_REVIEWER_EMAIL=bugdaddy.in@gmail.com \
    JIRA_REVIEWER_DISPLAY_NAME=BugDaddy \
    GITHUB_TOKEN=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

COPY pyproject.toml ./
COPY main.py ./
COPY agentic_solution ./agentic_solution

RUN uv pip install . \
    && uv pip install "aws-opentelemetry-distro>=0.10.1"

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080

CMD ["opentelemetry-instrument", "python", "main.py"]
