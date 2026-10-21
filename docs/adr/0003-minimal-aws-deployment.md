# ADR 0003: Minimal AWS deployment under $1.99 a month

- Status: accepted
- Date: 2026-10-21

## Context

The API must be public for the demo, cost at most $1.99 a month, and use only the services it
needs. The image needs about 1 GB of files the repository cannot hold: the LOINC table (its
licence forbids redistribution), the trained NER model (278 MB), the embedding model (465 MB)
and its caches (209 MB). The service takes about 14 s to start and peaks at 2.85 GB of memory.

## Decision

| Service | Why it is needed | Monthly cost |
|---|---|---|
| Lambda + function URL (3.5 GB memory) | Runs the API; the URL is free | $0 within the free tier for demo traffic |
| ECR, lifecycle keeps 2 images | Lambda runs images from ECR | ~$0.22 |
| S3, private, encrypted | Build inputs the repository cannot hold; never user data | ~$0.03 |
| SSM Parameter Store (standard) | The Gemini key | $0 |
| CloudWatch Logs, 7-day retention | Debugging | $0 |
| AWS Budgets + SNS + a 15-line kill-switch function | Enforces the cap | $0 |

About $0.25 a month in total. Two CloudFormation stacks: `infra/bootstrap.yaml`, created once
by an admin in the console (deploy role, ECR, bucket, key parameter, cost guard), and
`infra/template.yaml`, deployed by GitHub Actions through OIDC, so no AWS keys are stored.

**The cap.** AWS has no hard spending limit; budgets only alert. A public URL hammered without
pause could cost tens of dollars a month. So the budget's 90% alarm publishes to SNS, which
runs a function that sets the API's reserved concurrency to 0, switching it off. The cost guard
lives in the admin stack, so a deploy cannot remove it. The budget counts only resources tagged
`project=nwoma`, which needs the tag activated once in Billing > Cost allocation tags.

Lambda Web Adapter runs the FastAPI app unchanged, with asynchronous initialisation for the
14 s start-up.

## Left out, and when they would be added

- **API Gateway**: rate limiting and API keys per client. Add with paying clients.
- **CloudFront**: caching and a custom domain. Add with real traffic or a domain.
- **VPC, NAT**: private networking to hospital systems. Add with a records-system integration.
- **Secrets Manager**: rotation for a billed LLM key. The free-tier key has billing off, so
  Parameter Store is enough; add with a paid key.
- **Storage (S3 for documents, DynamoDB)**: Nwoma stores nothing; add with audit-log
  requirements (Hospital tier).

## Consequences

- Cold starts take about 15 s; the first request after idle is slow. Provisioned concurrency
  would fix it and cost money, so it is left out.
- If the account's total Lambda limit is 10, AWS refuses the reservation of 1; set the
  repository variable `RESERVED_CONCURRENCY=none`. The kill switch works either way.
