# BugDaddy Complete Architecture (HLD + LLD)

This document provides end-to-end architecture diagrams for the complete `bug_daddy` project.

## 1. High-Level Design (HLD)

```mermaid
flowchart TB
    U[Operators / Developers]
    FE[BugDaddy Frontend\nNext.js static export]
    API[Platform Backend API\nFastAPI on :8000]
    DB[(MySQL RDS\nbug_daddy)]

    AG[Agent Runtime\nAWS Bedrock AgentCore\nincident/bug/reviewer/sme/classifier/feature]
    SQS[SQS AI Automation Queue]
    JIRA[Jira Cloud]
    GH[GitHub / Bitbucket]
    CW[CloudWatch Logs]
    LOG_L[LogMonitoringBot Lambda]
    SONAR_L[Sonar Trigger Lambda]
    SONAR_EC2[Sonar Runner EC2\nDocker SonarQube + Scanner]
    SONAR_S3[(S3 Sonar Reports)]
    SONAR_ING[SonarReportIngestor Lambda]
    SEC[Security Scanner Worker\ninside backend async jobs]
    AWSINV[AWS APIs\nEC2/Lambda/ECR/ECS inventory]
    TX[Transaction Management Service\nFastAPI :8005]
    PG[(PostgreSQL app DB)]
    RAG[RAG Engine\nrag/* modules in backend]
    KB[(RAG PGVector Store)]

    U --> FE
    FE --> API
    API --> DB

    API --> AG
    API --> SQS
    API --> JIRA
    AG --> JIRA
    AG --> GH

    CW --> LOG_L --> DB
    JIRA -->|Webhook| API

    API --> SONAR_L --> SONAR_EC2
    SONAR_EC2 --> SONAR_S3
    SONAR_S3 --> SONAR_ING --> DB

    API --> SEC --> AWSINV
    SEC --> DB

    API --> TX --> PG
    API --> RAG --> KB
```

## 2. Low-Level Design (LLD)

```mermaid
flowchart LR
    subgraph Frontend["platform/frontend (Next.js App Router)"]
      Login[Login/Reset]
      Dash[DashboardApp]
      Issues[IssuesView + ExecutionGraphModal]
      Support[SupportChatWidget]
      Admin[Admin + Queue controls]
      Lib[src/lib/api.ts + storage.ts]
      Login --> Lib
      Dash --> Lib
      Issues --> Lib
      Support --> Lib
      Admin --> Lib
    end

    subgraph Backend["platform/backend/main.py (FastAPI)"]
      Auth[Auth + RBAC + sessions]
      IssueCore[Issue APIs\n/issues, /dashboard, /feed]
      AgentOrch[Agent Orchestration\n/agent/invoke, /agent/executions]
      SonarAPI[Sonar APIs\n/sonar/*]
      SecurityAPI[Security APIs\n/security/*]
      TxDemo[Transaction Demo APIs\n/demo/transaction/*]
      SupportAPI[Support APIs\n/support/*]
      QueueW[AI Queue workers\nbackground threads + SQS polling]
    end

    subgraph AgentCore["agents/apps/bug_daddy"]
      Router[CombinedBugDaddyRuntime]
      Inc[incident_daddy]
      Bug[bug_daddy]
      Rev[reviewer_daddy]
      SME[sme_agent]
      Clf[classifier]
      Feat[feature_daddy]
      Router --> Inc
      Router --> Bug
      Router --> Rev
      Router --> SME
      Router --> Clf
      Router --> Feat
    end

    subgraph RAG["platform/backend/rag"]
      RApi[rag.api.router]
      Ingest[rag.ingestion.pipeline]
      Ret[rag.retrieval.engine]
      Bed[rag.services.bedrock]
      RDB[(rag_* tables + embeddings)]
      RApi --> Ret
      RApi --> Bed
      RApi --> RDB
      Ingest --> RDB
    end

    subgraph Ingestion["Event Ingestion"]
      LogBot[triggers/LogMonitoringBot]
      SonarIn[triggers/SonarReportIngestor]
      JiraWH[/webhooks/jira handler/]
    end

    subgraph Security["Security Scanner Flow"]
      SecRun[run_security_scan_background]
      Inv[aws_inventory.py]
      Ext[lambda_package_extractor.py]
      CVE[cve_lookup.py]
      SecRun --> Inv --> Ext --> CVE
    end

    subgraph Sonar["sonar/* kit"]
      SLambda[sonar/lambda_function.py]
      SEC2[EC2 runner + docker-compose sonarqube/scanner]
      SS3[(S3 report.json)]
      SLambda --> SEC2 --> SS3
    end

    subgraph TxSvc["SME/backend/transaction_management"]
      TxAPI[Transfer + Reconciliation APIs]
      TxBug[Intentional bug/fix endpoints]
      TxObs[Metrics + Query monitoring]
      TxPG[(PostgreSQL schemas)]
      TxAPI --> TxPG
      TxBug --> TxPG
      TxObs --> TxPG
    end

    FE -->|REST/SSE| Backend
    SupportAPI --> RApi
    AgentOrch --> Router
    QueueW --> Router

    IssueCore --> My[(MySQL bug_daddy)]
    Auth --> My
    AgentOrch --> My
    SonarAPI --> My
    SecurityAPI --> My
    SupportAPI --> My

    TxDemo --> TxAPI
    TxDemo --> TxBug
    TxDemo --> TxObs

    LogBot --> My
    SonarIn --> My
    JiraWH --> IssueCore

    SonarAPI --> SLambda
    SS3 --> SonarIn
    SecurityAPI --> SecRun
```

## 3. Core Runtime Sequence (Issue to Automated Resolution)

```mermaid
sequenceDiagram
    participant CW as CloudWatch/Sonar/Jira
    participant ING as Ingestion (Lambda/Webhook)
    participant DB as MySQL bug_daddy
    participant FE as Frontend
    participant API as Backend FastAPI
    participant AG as AgentCore Runtime
    participant SCM as GitHub/Bitbucket/Jira

    CW->>ING: Emit issue event
    ING->>DB: Upsert service_exception_log
    FE->>API: Open dashboard + prioritize issue
    API->>DB: Read/update issue status
    API->>AG: /agent/invoke(target inferred or explicit)
    AG->>SCM: Gather context, propose fix/review/escalation
    AG-->>API: Execution events + outcome
    API->>DB: Persist session/events/resolution links
    API-->>FE: Live graph/feed + final status
```
