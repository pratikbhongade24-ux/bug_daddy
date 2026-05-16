import hashlib
import json
import os
from typing import Any

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


class BedrockClient:
    def __init__(self) -> None:
        session_kwargs: dict[str, str] = {}
        profile = (settings.aws_profile or '').strip()
        if not profile:
            if (os.getenv('AWS_PROFILE') or '').strip() == '':
                os.environ.pop('AWS_PROFILE', None)
            if (os.getenv('AWS_DEFAULT_PROFILE') or '').strip() == '':
                os.environ.pop('AWS_DEFAULT_PROFILE', None)
        if profile:
            session_kwargs['profile_name'] = profile

        session = boto3.Session(**session_kwargs)

        client_kwargs: dict[str, str] = {'region_name': settings.aws_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            client_kwargs['aws_access_key_id'] = settings.aws_access_key_id
            client_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key
            if settings.aws_session_token:
                client_kwargs['aws_session_token'] = settings.aws_session_token

        self.runtime = session.client('bedrock-runtime', **client_kwargs)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def embed(self, text: str) -> list[float]:
        if settings.use_mock_bedrock:
            digest = hashlib.sha256(text.encode('utf-8')).digest()
            seed = [b / 255 for b in digest]
            out = []
            while len(out) < 1024:
                out.extend(seed)
            return out[:1024]
        payload = {'inputText': text}
        response = self.runtime.invoke_model(
            modelId=settings.bedrock_embedding_model,
            body=json.dumps(payload),
            contentType='application/json',
            accept='application/json',
        )
        body = response['body'].read().decode('utf-8')
        data = json.loads(body)
        return data['embedding']

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def generate(self, prompt: str) -> str:
        if settings.use_mock_bedrock:
            return (
                'Mock response (local mode): Bedrock is disabled. '
                'Configure AWS credentials and set USE_MOCK_BEDROCK=false for real responses.'
            )
        payload: dict[str, Any] = {
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.1,
            'max_tokens': 1800,
        }
        response = self.runtime.invoke_model(
            modelId=settings.bedrock_llm_model,
            body=json.dumps(payload),
            contentType='application/json',
            accept='application/json',
        )
        body = response['body'].read().decode('utf-8')
        data = json.loads(body)
        if isinstance(data.get('output'), str):
            return data['output']
        if data.get('choices'):
            return data['choices'][0].get('message', {}).get('content', '')
        return str(data)


bedrock_client = BedrockClient()
