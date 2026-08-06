
# Production Operations and Safety Gate

RoboWeaver is production-shaped software, not a certified functional-safety system.
The compiler, API, and containers can be deployed for research and simulation. A
physical robot must remain supervised and protected by an independent, validated
safety controller until every hardware gate below has objective evidence.

## Supported Runtime

- Python 3.10 through 3.12; CI tests 3.10 and 3.12.
- Node.js 22 for the Next.js frontend.
- The API defaults to loopback and needs no token for local development.
- Any non-loopback bind requires `ROBOWEAVER_API_TOKEN` at startup.
- Browser origins outside localhost must be exact entries in
  `ROBOWEAVER_ALLOWED_ORIGINS`; wildcards are intentionally unsupported.

Generate a token without storing it in shell history:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never put the token in a `NEXT_PUBLIC_*` variable. Those values are compiled into the
browser bundle. The included Next.js same-origin proxy reads `ROBOWEAVER_API_TOKEN`
only on the server, validates upstream paths, bounds request bodies, sets timeouts, and
does not follow upstream redirects. Remote access must additionally sit behind a
gateway that terminates TLS and establishes an authenticated, expiring operator
session. The browser may call the loopback API directly during local development.

The dashboard API is built on Python's standard-library HTTP server. It is suitable
for local and internal service use, but it is not a hardened internet-facing edge
server. Never publish port 8080 directly to the internet. Keep it on loopback or an
internal container network behind the frontend and a production reverse proxy.

Resource controls can be tuned within their validated ranges:

```bash
ROBOWEAVER_MAX_CONCURRENT_REQUESTS=32
ROBOWEAVER_RATE_LIMIT_PER_MINUTE=240
ROBOWEAVER_EXPENSIVE_RATE_LIMIT_PER_MINUTE=30
```

Requests and responses are bounded, non-standard JSON numbers are rejected, request
IDs are sanitized, API logs omit query values, and generated identifiers cannot
escape their output directories. These are application safeguards, not a substitute
for network segmentation, monitoring, backups, or an incident-response process.

## Container Baseline

```bash
cp .env.example .env
# Replace the placeholder token in .env.
docker compose up --build
```

The containers run as non-root users with a read-only filesystem, dropped Linux
capabilities, `no-new-privileges`, bounded temporary filesystems, and loopback-only
published ports. `/health/live` and `/health/ready` are available for orchestration.

Hardware access such as `/dev/ttyUSB0`, SocketCAN, ROS 2 host networking, or a DDS
domain is deliberately not granted by the default Compose file. Add each device or
network permission explicitly for a controlled laboratory deployment.

## Mandatory Physical-Robot Gate

Do not authorize unsupervised physical execution until all of the following are
implemented and validated for the exact robot/controller combination:

- Independent emergency stop and safety-rated protective stop.
- Controller heartbeat/watchdog with a tested communications-loss safe stop.
- Measured joint-state feedback and trajectory acceptance/completion acknowledgement.
- Collision and self-collision models validated against the physical cell.
- Joint velocity, acceleration, effort/torque, payload, and thermal limits.
- Human exclusion zones, safety scanner inputs, and mode-dependent speed limits.
- Calibration, tool-center-point, payload, and frame provenance checks.
- Fault injection for dropped packets, stale state, controller rejection, and restart.
- Hardware-in-the-loop regression tests and a documented operator recovery procedure.
- Risk assessment and approval under the institution's applicable machinery and robot
  safety standards.

RoboWeaver now fails deployment when compile diagnostics contain errors, simulation
validation fails, or a bridge rejects any trajectory segment. TCP reachability alone
never counts as simulator trajectory delivery. These controls are defense in depth;
they do not replace the independent safety functions above.

## Release Checklist

1. Run `python -m pytest tests/ -q` on a supported Python version.
2. Run `python -m build` and install the wheel in a clean environment.
3. Run `npm ci`, `npm run lint`, `npx tsc --noEmit`, and `npm run build` in `frontend/`.
4. Run `pip-audit`, Bandit, the full npm audit, and review CodeQL results.
5. Build and scan both container images; record image digests and an SBOM.
6. Verify secrets are supplied by the deployment platform, not image layers or Git.
7. Exercise liveness/readiness, backup, rollback, and incident-stop procedures.
8. For hardware, attach the completed physical-robot safety evidence to the release.
