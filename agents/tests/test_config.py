from agentic_solution.config import AppConfig


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
    assert config.bedrock_model_id == "anthropic.claude-haiku-4-5-20251001-v1:0"
