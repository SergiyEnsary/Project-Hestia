# Hestia

[![Coverage Status](https://coveralls.io/repos/github/SergiyEnsary/Project-Hestia/badge.svg?branch=main)](https://coveralls.io/github/SergiyEnsary/Project-Hestia?branch=main)

**Hestia** is a local-first home assistant AI. She runs on your home server with [Ollama](https://ollama.com), delegates to Greek-named capability modules, and is consulted through **Pythia** (web chat).

**Repository:** [github.com/SergiyEnsary/Project-Hestia](https://github.com/SergiyEnsary/Project-Hestia)

See the full architecture plan in [docs/PLAN.md](docs/PLAN.md).

## Pantheon

| Name | Role |
|------|------|
| **Hestia** | Core AI, orchestrator, API |
| **Zephyrus** | Weather |
| **Kairos** | Calendar (Phase 2) |
| **Pythia** | Web chat UI |
| **Echo** | Voice interface (Phase 3) |
| **Mnemosyne** | Session memory |

## Quick start

### Prerequisites

- Python 3.11+
- **[Ollama](https://ollama.com)** — Hestia's local AI brain (required)
- Node.js 18+ (for Pythia dev UI)

### Install Ollama

1. Download and install from [ollama.com](https://ollama.com)
2. Open the Ollama app (or run `ollama serve` in a terminal)
3. Pull a model with tool support:

```bash
ollama pull llama3.1:8b
```

Verify Ollama is running:

```bash
curl http://127.0.0.1:11434/api/tags
```

You should get a JSON response listing models. If this fails, Hestia cannot chat.

### Setup

```bash
cd "Project Hestia"

# Create and activate the virtual environment (required before hestia works)
python3 -m venv .venv
source .venv/bin/activate

# Install Hestia into the venv (registers the `hestia` command)
pip install -e ".[dev]"

# Configure
cp config.yaml.example config.yaml
cp .env.example .env
openssl rand -hex 32   # paste into HESTIA_API_TOKEN in .env
```

### Run Hestia API

**From the project root** (not the `pythia` folder), with the venv activated:

```bash
source .venv/bin/activate   # if not already active
hestia serve
```

If `hestia` is still not found, use:

```bash
python -m hestia.main serve
```

### Pythia (React UI)

```bash
cd hestia/interfaces/pythia
npm install
npm run dev    # http://localhost:5173 — proxies API to :8000
```

Open Pythia, enter your `HESTIA_API_TOKEN` in settings, and chat with Hestia.

### Tests

```bash
source .venv/bin/activate
pytest tests/ -v --cov=hestia --cov-report=term-missing

cd hestia/interfaces/pythia
npm run test:coverage
```

GitHub Actions publishes backend and frontend coverage in the workflow summary
and attaches the full reports to each run. Coveralls combines both reports for
the coverage badge at the top of this page.

### Production

```bash
cd hestia/interfaces/pythia && npm run build
hestia serve   # serves API + built Pythia at http://127.0.0.1:8000
```

## Security

- All chat endpoints require `Authorization: Bearer <HESTIA_API_TOKEN>`
- Never commit `.env` or `config.yaml`
- See [SECURITY.md](SECURITY.md) for vulnerability reporting

## Adding a module

1. Pick an unused Greek mythological name
2. Create `hestia/modules/<slug>/module.py` implementing `HestiaModule`
3. Register in `config.yaml` under `modules.<slug>`
4. Add an entry to `hestia/modules/loader.py`

## License

MIT
