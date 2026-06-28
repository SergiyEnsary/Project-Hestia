# Plan Changelog

Revision history for [docs/PLAN.md](../PLAN.md). Update this file whenever the plan changes.

## 2025-06-23 — Phase 1 implemented

- Full scaffold: Python package, FastAPI API, security, Zephyrus weather module, Pythia React UI
- 7 unit tests passing (auth, orchestrator, Zephyrus)
- GitHub CI and gitleaks workflows added

## 2025-06-23 — AWS optional infrastructure

- AWS permitted for free/low-cost services only; home server remains default runtime
- Phase 2: optional S3 backups, SSM secrets, Bedrock LLM fallback (all disabled by default)
- Phase 4: Iris notifications via SES free tier; optional Lambda webhooks
- Cost guardrails: billing alarms, no AWS creds in git, provider abstractions in `hestia/providers/`

## 2025-06-23 — Initial plan

- Greenfield architecture: Python/FastAPI core, Ollama, modular Greek-named modules
- Phase 1: Hestia core, Zephyrus (weather), Pythia (React chat UI)
- Greek mythology naming convention for all modules and interfaces
- Security model for public repo: `.env` secrets, Bearer auth, gitleaks CI
- Secrets storage documented: `.env`, `config.yaml`, `~/.hestia/`, Pythia `sessionStorage`
- Plan saved to `docs/PLAN.md` for in-repo trackability
