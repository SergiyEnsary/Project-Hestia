# Module Authoring Contract

Hestia capabilities are isolated packages under `hestia/modules/<slug>/`.
This document is the acceptance contract for new modules.

## Before implementation

1. Pick an unused figure, deity, spirit, or muse from **Greek mythology**.
   Use the Greek name, not a Roman or other equivalent. `hestia` is reserved.
2. Choose a lowercase transliterated slug. The package path, config key, log
   identity, and tool namespace all use this exact slug.
3. Write a one-line domain description and identify every external system,
   secret, data-retention need, and side effect.
4. Threat-model network access and all proposed `write` tools. Write tools
   cannot ship until exact-argument, one-use user confirmation is enforced by
   the orchestrator.

## Package and lifecycle contract

The implementation satisfies `HestiaModule` in `hestia/modules/base.py`:

```python
class ExampleModule(HestiaModule):
    slug = "example"
    display_name = "Example"
    domain = "One-line capability description"
    config_type = ExampleConfig

    async def setup(self, config: StrictConfig) -> None: ...
    async def teardown(self) -> None: ...
    def get_tools(self) -> list[RegisteredTool]: ...
```

- Subclass the abstract `HestiaModule` base and set `config_type` to the
  module's `StrictConfig` subclass. The loader verifies this pairing.
- `setup` receives only the module's validated config instance. Check or narrow
  it to `config_type`, create clients and acquire resources there, and use
  finite timeouts.
- `setup` must either complete fully or clean up partial resources before
  raising. It must not start untracked background work.
- `teardown` closes clients, files, tasks, and pools, is safe after partial
  setup, and does not leak exceptions that prevent other modules shutting down.
- `get_tools` is deterministic and returns only this module's tools.
- A module MUST NOT import another module, the API layer, or an interface.
  Shared non-domain behavior belongs in core or providers after review.
- A module owns its external clients and does not mutate global process state.

Add a strict Pydantic config model in `hestia/config.py`, nest it under
`modules.<slug>`, add a safe disabled/default example to
`config.yaml.example`, and register the class in
`hestia/modules/loader.py`. Unknown config keys must remain rejected. Secrets
are `${ENVIRONMENT_VARIABLE}` references, never literal example values.

## Tool contract

Each `RegisteredTool` pairs a `ToolDefinition` with one async handler.

- Name: `<slug>.<verb_noun>`, globally unique and stable.
- Description: states what the tool does without prompt instructions or secret
  data.
- Parameters: a closed JSON object schema with explicit types, required keys,
  length/range bounds, and no unknown keys.
- Risk: explicitly choose `RiskLevel.READ` or `RiskLevel.WRITE`; do not rely on
  the default during review.
- Handler: accepts validated arguments and returns a bounded string. Structured
  results should be JSON with stable, documented fields.

A `read` tool has no durable side effect. Network caching or access logging by
an upstream service does not turn a mutating operation into a read. Creating,
sending, updating, deleting, unlocking, purchasing, and device control are
always `write`.

Handlers must not execute shell commands, evaluate code, interpolate arguments
into SQL, or let the model choose arbitrary URLs. They must set timeouts and
size limits, validate redirects and destinations, and convert expected failures
to concise safe errors. Never return credentials, environment contents,
private calendar URLs, raw upstream error bodies, or stack traces.

The registry is the only route from the orchestrator to a tool. Do not add a
second dispatch mechanism or dynamically import classes named by config or
model output.

## Isolation and failure behavior

- Validate untrusted data at both the tool boundary and external-response
  boundary.
- One module's timeout, malformed response, or teardown failure must not crash
  Hestia or corrupt another module.
- Bound retries with backoff; do not retry authentication failures or unsafe
  writes automatically.
- Log the module slug and safe operation metadata, never secrets or private
  payloads. Use Hestia's centralized redaction.
- Keep user-visible output and logs bounded. Avoid logging full tool arguments.
- Store durable data only in the configured Hestia data directory. Apply
  restrictive permissions and a documented retention policy.

For URL-fetching modules, follow the SSRF requirements in
[SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md), including validation after
DNS resolution and on every redirect.

## Tests required for acceptance

Every module adds tests for:

- lifecycle setup, teardown, disabled configuration, and partial setup failure;
- metadata, unique names, complete bounded schemas, and declared risk levels;
- successful tool behavior and stable structured results;
- missing, unknown, wrong-type, oversized, and out-of-range arguments;
- upstream timeout, non-success status, malformed and oversized responses;
- secret redaction and safe user-facing errors;
- redirect and private/link-local/metadata destination denial for URL fetches;
- write confirmation denial, expiry, argument binding, and one-use behavior for
  every write tool; and
- any persistence migration, retention, concurrency, and restart behavior.

Mock external systems. Tests must not require live credentials, Ollama, public
internet access, or a developer's home-network services. Backend lint,
typecheck, tests, and coverage must pass before registration is accepted.

## Review checklist

- [ ] Greek identity and slug are unused and consistent.
- [ ] Config is strict, safe by default, and contains no literal secret.
- [ ] No cross-module/API/interface imports or global mutable client state.
- [ ] Tool schemas are closed and bounded; risk levels are explicit.
- [ ] No arbitrary execution, arbitrary URL fetch, or secret-bearing output.
- [ ] Timeouts, response limits, redirects, retries, and teardown are bounded.
- [ ] Write tools have tested exact-argument confirmation or remain disabled.
- [ ] Required denial-path, redaction, and lifecycle tests are present.
- [ ] User and security documentation describe new data and permissions.
