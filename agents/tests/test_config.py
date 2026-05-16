from agentic_solution.config import AppConfig
from agentic_solution.jira_tools import get_native_jira_tools, native_jira_diagnostics


def test_config_reads_json_lists(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("SLACK_MCP_COMMAND", "npx")
    monkeypatch.setenv("SLACK_MCP_ARGS", '["-y","slack-server"]')
    monkeypatch.setenv("SLACK_MCP_TOOL_ALLOWLIST", '["create_channel","post_message"]')
    monkeypatch.setenv("BUG_DADDY_URL", "https://bug.example.com/invocations")
    monkeypatch.setenv("PEER_TIMEOUT_SECONDS", "12")

    config = AppConfig.from_env()

    assert config.aws_region == "ap-south-1"
    assert config.bedrock_model_id == "test-model"
    assert config.dry_run is True
    assert config.slack.command == "npx"
    assert config.slack.args == ["-y", "slack-server"]
    assert config.slack.tool_allowlist == ["create_channel", "post_message"]
    assert config.bug_daddy.url == "https://bug.example.com/invocations"
    assert config.peer_timeout_seconds == 12.0


def test_config_uses_boto3_region_when_env_missing(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.setattr("agentic_solution.config._region_from_boto3_session", lambda: "eu-west-1")

    config = AppConfig.from_env()

    assert config.aws_region == "eu-west-1"
    assert config.bedrock_model_id == "qwen.qwen3-coder-480b-a35b-v1:0"


def test_native_jira_tools_are_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

    assert get_native_jira_tools() == []
    assert native_jira_diagnostics()["status"] == "disabled"


def test_native_jira_tools_are_enabled_with_credentials(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://bugdaddy.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "SCRUM")
    monkeypatch.setenv("JIRA_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")

    tools = get_native_jira_tools()

    assert len(tools) == 5
    assert native_jira_diagnostics()["project_key"] == "SCRUM"
