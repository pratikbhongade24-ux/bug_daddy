from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from strands import Agent
from strands.models import BedrockModel

from agentic_solution.config import AppConfig
from agentic_solution.db_tools import insert_exception_log, lookup_exception_log
from agentic_solution.execution import ExecutionLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SLACK_INTAKE_PROMPT = """
You are Bug Daddy Slack Intake, a conversational agent that helps engineers report bugs and
service exceptions via Slack. Your job is to gather all the information needed to log an issue
in the bug tracking system, then insert it.

REQUIRED FIELDS — you must collect ALL of these before inserting:
  1. service_name   – which service or microservice is affected? (e.g. "loan-service", "auth-api")
  2. issue_type     – one of: bug | incident | tech_debt | cve | other
  3. description    – a clear one-to-three sentence description of what went wrong

OPTIONAL FIELDS — ask for these if the user mentions them or if they are relevant:
  4. stack_trace    – any error stacktrace or log snippet
  5. assigned_to    – email or name of the person owning this issue
  6. resolution_jira – an existing Jira ticket key (e.g. SCRUM-123), if one already exists

CONVERSATION RULES:
- Ask for missing required fields one at a time in a friendly, concise way.
- Never ask for fields the user has already provided.
- Once you have all required fields, confirm the details with the user in a short summary and ask
  "Shall I log this? (yes / no / edit <field>)".
- Only call insert_exception_log after the user explicitly confirms with "yes" or an affirmative.
- If the user says "edit <field>", ask for the new value for that field and re-confirm.
- After a successful insert, reply with:
  "Done! Issue logged.
   ID: <id>
   Jira: <resolution_jira or 'none'>
   Fingerprint: <fingerprint>"
- If a duplicate fingerprint already exists (check with lookup_exception_log before inserting),
  tell the user: "This looks like a duplicate of existing issue #<id> (<fingerprint>). Do you
  still want to log a new entry? (yes / no)"
- Keep all responses short and Slack-friendly. Use plain text, not markdown headers.
- source is always "slack" — do not ask the user for it.
""".strip()


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SlackIntakeRuntime:
    config: AppConfig

    def _build_agent(self, session_id: str | None) -> Agent:
        model = BedrockModel(
            model_id=self.config.bedrock_model_id,
            region_name=self.config.aws_region,
            temperature=0.2,
        )
        # Bedrock AgentCore memory is injected automatically by the SDK when a
        # memory_id is present in .bedrock_agentcore.yaml and a session_id is
        # passed on the invocation context.  The Strands Agent picks it up via
        # the BedrockModel's built-in conversation history when the runtime is
        # called with the same session_id across turns.
        return Agent(
            model=model,
            system_prompt=SLACK_INTAKE_PROMPT,
            tools=[insert_exception_log, lookup_exception_log],
        )

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        execution_logger = ExecutionLogger.from_payload(payload, "slack_intake")

        # The user's message lives in "prompt" or "message"
        user_message = (
            payload.get("prompt")
            or payload.get("message")
            or payload.get("text")
            or ""
        ).strip()

        if not user_message:
            return {
                "component": "slack_intake",
                "reply": (
                    "Hi! I'm Bug Daddy. Tell me about the issue you'd like to log — "
                    "what service is affected and what went wrong?"
                ),
            }

        session_id = (
            payload.get("session_id")
            or payload.get("slack_thread_ts")
            or payload.get("thread_ts")
        )

        started = execution_logger.node_started(
            "intake", "Slack Intake", "Process user message", user_message
        )

        agent = self._build_agent(session_id)
        reply = str(agent(user_message))

        execution_logger.node_completed(
            "intake", "Slack Intake", "Reply generated", started, reply
        )

        return {
            "component": "slack_intake",
            "session_id": session_id,
            "reply": reply,
        }


def build_runtime(config: AppConfig | None = None) -> SlackIntakeRuntime:
    cfg = config or AppConfig.from_env()
    return SlackIntakeRuntime(config=cfg)
