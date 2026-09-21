# JudgeOps

JudgeOps is OpenModelOps' governed LLM-as-a-judge layer. It complements Ragas
and DeepEval by making the judge itself a versioned, testable and auditable
production dependency.

## Implemented controls

- Versioned RAG, agent and high-risk numeric rubrics with content digests.
- Strict JSON result contracts with no silently accepted extra fields.
- Exact dimension validation and normalized scores from zero to one.
- Candidate, reference, context and tool-expectation evaluation inputs.
- Deterministic development judge clearly identified as non-LLM evidence.
- OpenAI-compatible judge provider for the local Metal runtime or another model.
- Judge-targeting prompt-injection screening and mandatory human review.
- Multi-judge median aggregation, confidence policy and disagreement routing.
- Pairwise forward/reversed evaluation for position-bias detection.
- Human-label calibration with accuracy, false-pass rate, false-fail rate and
  Cohen's kappa.
- Worst-case per-dimension adapter into the existing fail-closed release gate.
- Prometheus request and latency telemetry.

## Trust model

```text
Versioned evaluation cases
           |
Deterministic security and schema checks
           |
Independent judge model(s)
           |
Disagreement / confidence / injection policy
           |
Pass ----- Fail ----- Human review
           |
Worst-case release metrics + signed evidence
           |
Independent release approver
```

An LLM verdict never replaces deterministic access-control, privacy, arithmetic,
schema or tool-authorization checks. High-risk cases should use at least two
different judge model families plus resolved human labels.

## Run locally

The deterministic provider exercises contracts without presenting itself as an
LLM evaluation:

```bash
PYTHON=.venv/bin/python make run-judgeops
```

Use the native Metal runtime as an OpenAI-compatible judge:

```bash
JUDGE_PROVIDER=openai-compatible \
JUDGE_MODEL_BASE_URL=http://127.0.0.1:8008 \
JUDGE_MODEL_ID=mlx-community/Qwen3-0.6B-4bit \
PYTHON=.venv/bin/python make run-judgeops
```

The 0.6B model is only an integration test. It is not an acceptable production
judge for high-risk decisions.

## Release requirements

A production judge revision should not be promoted until it meets a documented
policy such as:

| Measure | Example gate |
|---|---:|
| Human-labelled calibration cases | >= 200 |
| Cohen's kappa | >= 0.75 |
| False-pass rate, high-risk cases | <= 2% |
| Pairwise order consistency | >= 95% |
| Structured-output validity | >= 99.5% |
| Unresolved human-review cases | 0 |

Thresholds must be selected for the domain rather than copied blindly from this
example. Banking, operational remediation and autonomous tool use require more
conservative false-pass policies than low-risk content ranking.

## Remaining qualification work

- Curate 200–500 independently labelled cases across RAG, agent and numeric
  workflows.
- Add a second model-family provider and repeated-run variance measurement.
- Persist immutable per-case results and human adjudication history.
- Sample production traces using privacy-preserving redaction and consent rules.
- Measure cost, latency and score drift for every judge revision.
- Add adversarial multilingual and multimodal judge-injection datasets.
