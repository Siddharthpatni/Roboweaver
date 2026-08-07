# Contributing to RoboWeaver

RoboWeaver accepts human-written and AI-assisted contributions under the same rule:
the submitting human owns the change and must be able to explain, test, and maintain
it. Generated volume is not evidence of quality.

## Required contribution evidence

Every pull request must:

1. State the user-visible problem and the exact boundary of the change.
2. Disclose material AI assistance, including the tool or model, without pasting
   credentials, private prompts, proprietary source, or personal data.
3. Identify security, safety, privacy, and compatibility risks. Robot motion,
   hardware bridges, generated controller code, and deployment gates require an
   explicit failure-mode analysis.
4. Include focused regression tests that fail without the change. A generated test
   that only repeats the implementation is insufficient.
5. Run the repository's backend, frontend, packaging, and security checks relevant to
   the touched surface and attach the results.
6. Reconcile documentation and `MILESTONES.md` with the implementation. Unsupported
   behavior must remain explicit.

Maintainers may close bulk, speculative, duplicate, or unverifiable submissions
without line-by-line review. Automated agents must not open pull requests, issues, or
security reports without a human first reproducing the problem and accepting ongoing
responsibility for the submission.

## Robotics-specific acceptance bar

- AI output may annotate or advise; it cannot bypass deterministic compilation,
  diagnostics, simulation evidence, or deployment policy.
- New robot profiles must pass structural validation and cite the source of limits,
  geometry, payload, velocity, and protocol facts.
- New backends need target gating, safe failure behavior, generated-output tests, and
  an official syntax/build validation path where one exists.
- Physical-hardware claims require reproducible logs. Software-only tests cannot be
  described as hardware validation or safety certification.
- Any proof or formal-verification claim must state its model, assumptions, bounds,
  counterexample behavior, and unmodeled physics.

## Before opening a pull request

```bash
python -m pytest tests/ -q --cov=roboweaver --cov-branch --cov-fail-under=75
python -m ruff check src tests scripts

cd frontend
npm run lint
npm run typecheck
npm run build
```

Also run dependency and generated-package checks when those surfaces change. See
`.github/workflows/ci.yml` for the complete merge gate.
