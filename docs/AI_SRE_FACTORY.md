# OpenModelOps AI SRE Factory

The factory is the self-service control layer across MLOps, LLMOps, AgentOps and AIOps. A team submits one immutable workload specification. The platform evaluates evidence, enforces separation of duties and permits provisioning and release only after every production gate passes.

```text
AI engineer / data scientist
            |
      workload specification
            |
     Factory control plane
            |
  +---------+---------+----------+---------+
  |                   |                    |
MLOps               LLMOps             AgentOps
training            fine-tuning        prompts/tools
registry            evaluation         guardrails
features            serving            feedback
  |                   |                    |
  +---------------- AI SRE ----------------+
        SLOs / telemetry / scorecards
        incidents / rollback / AIOps
```

## Factory contract

Every workload declares:

- workload kind, owner, tenant and environment;
- immutable artifact digest;
- data classification and network posture;
- GPU requirement;
- availability, latency and error-rate objectives.

Production approval requires passing evidence for security, quality, reliability, observability, cost and rollback. An owner or gate evaluator cannot approve the release. This makes the factory a governed delivery system rather than a collection of dashboards.

## API workflow

1. Submit a model, LLM, agent or RAG workload to `POST /workloads`.
2. Record signed or addressable gate evidence with `PUT /workloads/{id}/gates`.
3. Approve through an independent release role.
4. Provision through a platform controller.
5. Release through a deployment controller.
6. Suspend on an SLO or security breach and retain the audit history.

The factory API persists governance state in PostgreSQL and derives production actors from OIDC. The Kubernetes SRE runtime adds read-only scheduled inspection and a separate, disabled-by-default remediation boundary. Production rollout still requires environment-specific identity, secrets, networking, backup and telemetry configuration.

## Factory roadmap

| Layer | Current | Next production increment |
|---|---|---|
| Workload API and scorecard | Implemented | PostgreSQL and OIDC enforcement |
| MLOps lifecycle | Implemented core | MLflow registration and workflow executor |
| Open-weight LLM serving | Ollama/vLLM adapters | GPU autoscaling and routing |
| Agent safety | Guardrails and controlled tools | Durable traces and sandboxed executors |
| AIOps | Approval workflow plus allow-listed Kubernetes scale/restart actions | Verification runbooks and incident integrations |
| AI SRE | SLO model and probes | OTel collector, alerts and burn-rate policies |
| Local infrastructure | Compose profiles and read-only Kubernetes SRE deployment | Kubernetes operators and GitOps |
| Cloud | Portable contracts | AWS Terraform and GitHub OIDC |
