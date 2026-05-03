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
    JIRA_EMAIL=pratikbhongade24@gmail.com \
    JIRA_API_TOKEN=ATATT3xFfGF0miJo7VrfqMwbGNbCBroNsEEVQFBwU8OpCVVxVgY7OOsm-ysvJufT2Hd3MfTw3TDy8GUVrUOx1vH9duan3ajPtETHIO_Uyt6pARASDXcDZky6lwzb8R0SPyfa1C5ia8h485XWvdqG9biQYgVVsTnQ3OwkUw29dXraxvg8ok5Q-yc=34851ECF \
    JIRA_PROJECT_KEY=BUG \
    JIRA_REVIEWER_ACCOUNT_ID=712020:135d0171-c856-4856-a910-674b8bfd7a2d \
    JIRA_REVIEWER_EMAIL=pratikbhongade24@gmail.com \
    JIRA_REVIEWER_DISPLAY_NAME=Pratik\ Bhongade \
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
