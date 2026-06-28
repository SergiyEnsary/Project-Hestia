# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

If you discover a security issue in Hestia, please report it privately by emailing the repository maintainer or opening a GitHub Security Advisory on this repository.

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to acknowledge reports within 48 hours.

## Security practices

- Never commit `.env`, `config.yaml`, or API tokens
- Generate `HESTIA_API_TOKEN` with `openssl rand -hex 32`
- Keep Ollama bound to `127.0.0.1` — do not expose port 11434 publicly
- Use a reverse proxy with TLS for remote access to Pythia
- Set an AWS billing alarm if you enable optional cloud features
