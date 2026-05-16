# AWS Deployment Blueprint (Embeddable Widget Mode)

## Target Architecture
- API Compute: ECS Fargate service for `rag-backend`
- Widget Delivery: host app static assets/CDN (serve `widget/chat-widget.js`)
- Vector Store: Aurora PostgreSQL (pgvector enabled)
- Cache: ElastiCache Redis
- Object Store: S3 (`sme-rag-documents`)
- LLM/Embeddings: Amazon Bedrock
  - Embedding: `amazon.titan-embed-text-v2:0`
  - Inference: `qwen.qwen3-coder-30b-a3b-v1:0`
- Secrets: AWS Secrets Manager + IAM roles
- Monitoring: CloudWatch + X-Ray + structured audit logs

## Network
- VPC with public ALB and private subnets for ECS/Aurora/Redis
- Security groups:
  - ALB -> ECS: 8010
  - ECS -> Aurora: 5432
  - ECS -> Redis: 6379

## Aurora Setup
1. Provision Aurora PostgreSQL-compatible cluster.
2. Install `pgvector` extension.
3. Apply `backend/sql/001_rag_schema.sql`.
4. Enable Performance Insights.

## Bedrock Access
- Enable model access for both required models in AWS account.
- Attach IAM policy for `bedrock:InvokeModel` to backend task role.

## CI/CD
- GitHub Actions builds backend image.
- Push to ECR.
- Deploy via ECS rolling update.
- Widget JS distributed via host app CDN/static pipeline.

## Hardening Checklist
- Enforce HTTPS and WAF on ALB.
- API key rotation via Secrets Manager.
- Per-tenant metadata isolation filter.
- Audit log retention policy and SIEM export.
