# Python 3.13 + Node 22 LTS in one slim image — no apt-get needed for Node
FROM nikolaik/python-nodejs:python3.13-nodejs22-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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
    GITHUB_TOKEN=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 \
    SLACK_BOT_TOKEN=xoxb-10824136099831-11090936545382-IXSCRE6SLUQsbHvq1egZkICP \
    SLACK_TEAM_ID=T0AQ8402XQF \
    SLACK_DEFAULT_CHANNEL=C0B2QUEU4NN \
    SLACK_MCP_TRANSPORT=stdio \
    SLACK_MCP_COMMAND=npx \
    SLACK_MCP_ARGS='["-y","@modelcontextprotocol/server-slack"]' \
    SLACK_MCP_TOOL_ALLOWLIST='["slack_post_message","slack_list_channels","slack_get_channel_history","slack_join_channel"]'

COPY pyproject.toml ./
COPY main.py ./
COPY agentic_solution ./agentic_solution

RUN uv pip install . \
    && uv pip install "aws-opentelemetry-distro>=0.10.1"

USER pn

EXPOSE 8080

CMD ["opentelemetry-instrument", "python", "main.py"]
