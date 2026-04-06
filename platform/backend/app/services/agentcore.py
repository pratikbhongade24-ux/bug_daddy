from __future__ import annotations

import json
from typing import Any
from urllib import parse, request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from app.core.config import get_settings


class AgentCoreRuntimeClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def invoke(self, runtime_arn: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        if not runtime_arn:
            raise RuntimeError(
                "AgentCore runtime ARN is required. "
                "Set the corresponding *_RUNTIME_ARN environment variable."
            )

        encoded_arn = parse.quote(runtime_arn, safe="")
        url = (
            f"https://bedrock-agentcore.{self.settings.aws_region}.amazonaws.com/"
            f"runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        )
        body = json.dumps(payload).encode("utf-8")

        session = boto3.session.Session(region_name=self.settings.aws_region)
        credentials = session.get_credentials()
        if credentials is None:
            raise RuntimeError("AWS credentials were not found for AgentCore invocation.")

        aws_request = AWSRequest(
            method="POST",
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", self.settings.aws_region).add_auth(
            aws_request
        )

        signed_request = request.Request(
            url=url,
            data=body,
            headers=dict(aws_request.headers.items()),
            method="POST",
        )
        with request.urlopen(signed_request, timeout=self.settings.agentcore_timeout_seconds) as response:
            raw = response.read().decode("utf-8")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}


agentcore_client = AgentCoreRuntimeClient()
