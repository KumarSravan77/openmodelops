# JudgeOps evaluation dataset

OpenModelOps includes a reproducible 240-case **candidate** corpus covering four
domains equally:

| Domain | Cases | Pass candidates | Fail candidates |
|---|---:|---:|---:|
| Synthetic banking | 60 | 30 | 30 |
| Kubernetes remediation | 60 | 30 | 30 |
| RAG groundedness | 60 | 30 | 30 |
| Agent tool authorization | 60 | 30 | 30 |

The candidate file is generated from deterministic synthetic policies. It
contains no customers, employer data, production incidents, credentials or
private documentation. Its expected labels are useful for pipeline testing, but
they are **not represented as independent human labels**.

## Reproduce the candidate corpus

```bash
.venv/bin/python tools/generate_judge_dataset.py
```

The adjacent manifest records the case distribution, generator version and
SHA-256 digest. Regeneration must produce the same digest unless the generator is
intentionally versioned.

## Independent labeling

Two distinct reviewers must resolve each case independently. The database
primary key prevents one reviewer from labeling the same case twice. Agreement
promotes a case; disagreement remains a conflict for adjudication.

```bash
.venv/bin/python tools/label_judge_dataset.py --database labels.db label \
  --sample-id banking-001-pass --reviewer reviewer-a --verdict pass \
  --rationale "The answer exactly matches the supplied status evidence."

.venv/bin/python tools/label_judge_dataset.py --database labels.db label \
  --sample-id banking-001-pass --reviewer reviewer-b --verdict pass \
  --rationale "The answer is grounded and introduces no unsupported claim."

.venv/bin/python tools/label_judge_dataset.py --database labels.db export \
  --candidates evaluation/candidates/judgeops-240-synthetic.jsonl \
  --output evaluation/golden/judgeops-human-verified.jsonl
```

The golden-dataset loader rejects candidate or synthetic labels. Only records
marked `label_source: human` and `label_status: verified` can enter calibration.

## Review guidance

Reviewers should label the candidate answer, not the generator's expected label.
They must check correctness, grounding, unsupported claims, authorization and
risk. Reviewers should not see each other's label before submitting. Conflicts
require a third adjudicator; they must not be resolved by silently overwriting an
existing label.

Synthetic cases are the first qualification tier. Before consequential use, add
privacy-reviewed, de-identified production traces and adversarial cases covering
multilingual content, ambiguous evidence, judge injection, numeric edge cases,
tool sequencing and incomplete telemetry.
