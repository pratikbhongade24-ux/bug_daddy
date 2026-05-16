# SME RAG Platform (Embeddable)

This package is now optimized for embedding inside another application as a floating support chatbot.

## Included
- Backend RAG APIs (FastAPI)
- Ingestion and retrieval pipeline
- Bedrock integration
- Aurora pgvector schema
- Redis rate limiting
- Embeddable floating widget (`widget/chat-widget.js`)

## Removed by design
- Standalone user authentication flows
- Separate full chat dashboard application
- Independent frontend portal

## Run Backend Stack
```bash
cd rag_platform
docker compose -f docker-compose.rag.yml up --build
```

RAG API base: `http://localhost:8010/api/v1`

## Embed Widget in Host App
```html
<script src="/path/to/chat-widget.js"></script>
<script>
  window.SMEChatWidget.createWidget({
    apiBase: 'http://localhost:8010/api/v1',
    apiKey: 'change-widget-key',
    externalUserId: 'your-app-user-id',
    sessionId: 'current-session-id'
  });
</script>
```

## Required Headers
All backend endpoints are protected by API key:
- `x-api-key: <WIDGET_API_KEY>`
- `POST /api/v1/admin/reindex` requires admin header:
- `x-admin-key: <ADMIN_API_KEY>`

## Primary APIs
- `POST /api/v1/ingest`
- `POST /api/v1/admin/reindex`
- `POST /api/v1/uploads`
- `POST /api/v1/chat/stream`
- `GET /api/v1/conversations?external_user_id=...&session_id=...`
- `GET /api/v1/messages/{conversation_id}?external_user_id=...`
- `POST /api/v1/feedback`
- `GET /api/v1/metrics`

## Chat Payload Contract
```json
{
  "conversation_id": 123,
  "external_user_id": "user-abc",
  "session_id": "session-xyz",
  "question": "Explain KYC verification workflow",
  "filters": {"service_name": "kyc_service"}
}
```

## Notes
- Host app owns real identity/auth; RAG backend consumes identity context.
- For production, route widget traffic via your API gateway and rotate keys with Secrets Manager.
