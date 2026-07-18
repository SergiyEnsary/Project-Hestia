# Security Architecture

This document defines Hestia's security boundaries and mandatory controls. It is
normative: changes that weaken a **MUST** or **MUST NOT** requirement require a
documented threat-model review and tests.

## Assets and trust boundaries

Protected assets include API tokens, private calendar URLs, OAuth/device
credentials, conversation history, tool results, and local-network access.

Hestia crosses these trust boundaries:

1. **Browser to API.** Pythia is untrusted input. Every chat request is
   authenticated, rate-limited, size-limited, and validated server-side.
2. **API to model.** Model output is untrusted. It may select only explicitly
   registered tools and never becomes code, a shell command, SQL, or a URL
   fetch without a purpose-built validator.
3. **Core to modules.** Modules receive only their own configuration and tool
   arguments. A module must not read another module's state or secrets.
4. **Modules to external services.** Responses, redirects, content types, sizes,
   and timeouts are untrusted. Private/link-local targets are denied unless a
   narrowly documented feature explicitly permits them.
5. **Container to host.** The image runs as an unprivileged user with a
   read-only root filesystem. Only the configured data directory is writable.

Ollama is trusted as a local dependency but its output is still untrusted.
Hestia does not publish Ollama through Docker Compose. Keep Ollama bound to the
host or a private container network.

## Authentication and network exposure

- `POST /chat` and `POST /chat/stream` (SSE) MUST require
  `Authorization: Bearer <token>`. Missing and invalid credentials return the
  same generic `401` response.
- `HESTIA_API_TOKEN` MUST be generated from at least 32 random bytes. It MUST
  NOT appear in query strings, logs, config YAML, frontend build-time variables,
  or source control.
- `/health` is intentionally unauthenticated and MUST expose no credentials,
  private user data, stack traces, or secret-bearing URLs.
- Binding beyond loopback MUST fail closed unless authentication is enabled and
  a sufficiently strong token is present.
- CORS origins MUST be an explicit allowlist. Wildcard origins are forbidden
  when credentials are accepted.
- A reverse proxy providing TLS is required before access leaves the host.
  Do not directly forward port 8000 from an internet router.

Pythia may keep the token in `sessionStorage`; it MUST NOT use `localStorage`,
cookies without a reviewed CSRF design, `VITE_*` variables, or committed files.
Users should treat any script running in Pythia's origin as able to read the
session token.

## Secrets and configuration

Secrets live in environment variables or an explicitly configured secret
provider. `config.yaml` contains non-secret settings and `${VARIABLE}`
references only. Example files contain placeholders only.

The following are mandatory:

- `.env`, `config.yaml`, private keys, token files, databases, and `secrets/`
  remain ignored by Git and excluded from Docker build contexts.
- Mounted `.env` and `config.yaml` files are read-only. Runtime data is mounted
  separately and writable.
- Logging uses the central redaction path. Code MUST NOT log complete request
  headers, environment mappings, calendar URLs, exception payloads that may
  contain credentials, or raw secret-provider responses.
- Frontend bundles and container image layers MUST contain no runtime secrets.
- Secret rotation is performed by replacing the external secret and restarting
  Hestia. Images are never rebuilt to rotate a secret.

GitHub secret scanning and dependency update automation are defense in depth;
they do not make committing a secret acceptable. Revoke a leaked credential
before removing it from history.

## Tool and module execution

Only tools returned by enabled, registered modules are callable. Tool names
MUST be globally unique and namespaced as `<module-slug>.<action>`. Schemas
MUST reject missing, unknown, wrong-type, oversized, and out-of-range input.
Handlers MUST use validated arguments rather than model-generated prose.

Every tool declares a `risk_level`:

- `read`: observes data and causes no durable external change.
- `write`: creates, changes, sends, deletes, unlocks, purchases, or otherwise
  causes a durable side effect.

Write tools MUST NOT be enabled until the orchestrator implements and tests an
unambiguous, user-visible confirmation tied to the exact arguments and expiring
after one use. A model statement is not user confirmation. Bulk, destructive,
financial, security-sensitive, and physical-access actions require a dedicated
threat review even after generic confirmation exists.

Tool failures are isolated and returned as bounded errors. User-facing errors
MUST NOT include secrets, internal paths, raw upstream bodies, or stack traces.
The orchestrator enforces a finite tool-iteration limit.

See [MODULE_AUTHORING.md](MODULE_AUTHORING.md) for the implementation contract.

## External fetches and private data

Calendar URLs are bearer secrets. Kairos and future fetch modules MUST:

- permit only expected schemes (normally HTTPS);
- resolve and validate destinations before connecting, deny loopback,
  link-local, metadata, and private networks by default, and reject redirects
  unless a future reviewed client revalidates every hop;
- connect to the validated address while preserving the original TLS SNI and
  Host header, preventing a second DNS lookup from rebinding the destination;
- set connect/read timeouts, response-size limits, and a redirect limit;
- avoid forwarding credentials across origins;
- parse input with non-executing libraries and cap item/text counts; and
- redact the complete URL and calendar contents from logs and errors.

An explicit `allow_private_hosts` setting is for deliberate home-network
integrations. Enabling it expands the SSRF boundary and must be documented for
that deployment; cloud metadata and link-local addresses remain forbidden.

Conversation databases and backups contain private data. File permissions and
backup buckets MUST be private, encryption in transit is required, retention is
bounded by configuration, and restore operations must not overwrite active data
without operator confirmation. AWS integrations remain disabled by default and
must work without granting broad account permissions.

## Container deployment controls

The supplied container:

- runs as UID/GID 10001 with all Linux capabilities dropped;
- uses `no-new-privileges`, a read-only root filesystem, bounded PIDs, CPU, and
  memory, plus a small writable `/tmp`;
- publishes Hestia only on host loopback by default;
- mounts config and secrets read-only and `/var/lib/hestia` writable; and
- probes the unauthenticated `/health` endpoint.

Adjust resource limits to measured workload, but do not remove them silently.
The health response distinguishes Hestia availability from Ollama reachability;
an unavailable model should be alerted on even while the API process is alive.
Pin image digests in higher-assurance deployments and rebuild regularly for
base-image security updates.

## Required verification

Pull requests must pass:

- backend Ruff lint, mypy type checking, tests, and coverage reporting;
- frontend TypeScript checking, production build, tests, and coverage reporting;
- secret scanning; and
- focused tests for auth, redaction, config validation, tool schema/risk
  behavior, SSRF controls, persistence, and migrations when those areas change.

Security-sensitive changes require tests for denied cases, not only successful
paths. Review dependency and container changes for provenance and unnecessary
runtime privileges.

## Incident response

If exposure is suspected: stop external access, revoke and replace affected
credentials, preserve sanitized logs, identify the first affected version,
patch and test the control failure, then restore service. Do not paste secrets
into issues, chat, CI logs, or commit messages. Report repository
vulnerabilities through the process in [SECURITY.md](../SECURITY.md).
