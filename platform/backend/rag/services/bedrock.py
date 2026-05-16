import hashlib
import json
import os
from typing import Any

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

from rag.core.config import (
    BEDROCK_EMBEDDING_MODEL,
    BEDROCK_LLM_MODEL,
    USE_MOCK_BEDROCK,
)


class BedrockClient:
    def __init__(self) -> None:
        profile = (os.getenv("AWS_PROFILE") or "").strip()
        session_kwargs: dict[str, str] = {}
        if profile:
            session_kwargs["profile_name"] = profile
        else:
            os.environ.pop("AWS_PROFILE", None)
            os.environ.pop("AWS_DEFAULT_PROFILE", None)

        session = boto3.Session(**session_kwargs)
        client_kwargs: dict[str, Any] = {"region_name": os.getenv("AWS_REGION", "ap-south-1")}
        key_id = os.getenv("AWS_ACCESS_KEY_ID")
        secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        if key_id and secret:
            client_kwargs["aws_access_key_id"] = key_id
            client_kwargs["aws_secret_access_key"] = secret
            token = os.getenv("AWS_SESSION_TOKEN")
            if token:
                client_kwargs["aws_session_token"] = token

        self.runtime = session.client("bedrock-runtime", **client_kwargs)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def embed(self, text: str) -> list[float]:
        if USE_MOCK_BEDROCK:
            digest = hashlib.sha256(text.encode()).digest()
            seed = [b / 255 for b in digest]
            out: list[float] = []
            while len(out) < 1024:
                out.extend(seed)
            return out[:1024]
        response = self.runtime.invoke_model(
            modelId=BEDROCK_EMBEDDING_MODEL,
            body=json.dumps({"inputText": text}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(response["body"].read())["embedding"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def generate(self, prompt: str) -> str:
        if USE_MOCK_BEDROCK:
            return (
                "Mock response (local mode): Bedrock is disabled. "
                "Configure AWS credentials and set USE_MOCK_BEDROCK=false for real responses."
            )
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1800,
        }
        response = self.runtime.invoke_model(
            modelId=BEDROCK_LLM_MODEL,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        data = json.loads(response["body"].read())
        if isinstance(data.get("output"), str):
            return data["output"]
        if data.get("choices"):
            return data["choices"][0].get("message", {}).get("content", "")
        return str(data)


bedrock_client = BedrockClient()
