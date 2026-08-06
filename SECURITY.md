# Security Policy

## Supported versions

Security fixes are applied to the latest release and the `main` branch. Older
development snapshots are not maintained independently.

| Version | Supported |
|---|---|
| Latest release | Yes |
| `main` | Yes |
| Older releases | No |

## Report a vulnerability

Do not publish exploit details, credentials, internal robot addresses, controller
banners, or safety-system information in a public issue. Use the repository's
[private vulnerability report](https://github.com/Siddharthpatni/Roboweaver/security/advisories/new).
Include the affected commit or version, reproduction steps, impact, and any proposed
mitigation. Remove secrets and personal or operational data from logs and examples.

You should receive an acknowledgement within seven days. Validation, remediation,
and disclosure timing depend on severity and whether a hardware integration is
affected. A fix is not considered complete until regression coverage and release
guidance are available.

## Scope

Reports are especially useful for:

- authentication, authorization, same-origin proxy, request parsing, or SSRF issues;
- generated-file traversal or unsafe generated code;
- robot bridge selection, protocol confusion, or fail-open deployment behavior;
- dependency or container supply-chain vulnerabilities;
- secrets or internal network data appearing in logs, responses, or browser bundles;
- denial-of-service paths that bypass request, concurrency, or resource bounds; and
- AI output that can bypass deterministic compilation, verification, or safety gates.

RoboWeaver is not a certified functional-safety controller. A report about unsafe
motion or hardware behavior is still in scope, but operators must first use the
independent emergency stop and follow their site incident procedure. Do not test a
suspected vulnerability on a physical robot, production cell, or network you do not
own or have explicit permission to assess.
