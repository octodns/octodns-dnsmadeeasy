# Developer Agent Guide for octoDNS DNS Made Easy Provider

This repository contains the DNS Made Easy provider for octoDNS. It enables planning, syncing, and applying DNS record states to the DNS Made Easy platform.

> [!IMPORTANT]
> **Core Workflow and Guidelines**
>
> All agents working on this repository must read and follow the general instructions and workflow guidelines defined in the core octoDNS `AGENTS.md` file.
> - **Local check**: Look for the file at `../octodns/AGENTS.md`.
> - **Remote check**: If the local file is not available, fetch it from GitHub: [octoDNS Core AGENTS.md](https://github.com/octodns/octodns/raw/refs/heads/main/AGENTS.md).
>
> You must align your code structure, style, pull request guidelines, and overall development workflows with the instructions specified there.

## Repository & Module Information

### Key Components

- **Provider Class**: [DnsMadeEasyProvider](file:///home/ross/octodns/octodns-dnsmadeeasy/octodns_dnsmadeeasy/__init__.py#L402-L499) (defined in [octodns_dnsmadeeasy/__init__.py](file:///home/ross/octodns/octodns-dnsmadeeasy/octodns_dnsmadeeasy/__init__.py)). This is the primary provider class orchestrating domain updates.
- **Client Class**: [DnsMadeEasyClient](file:///home/ross/octodns/octodns-dnsmadeeasy/octodns_dnsmadeeasy/__init__.py#L43-L400) communicates with DNS Made Easy REST API v2.0.
- **Authentication & Security**: Security uses custom HTTP headers:
  - `x-dnsme-apiKey`: API Key.
  - `x-dnsme-requestDate`: GMT HTTP-date timestamp.
  - `x-dnsme-hmac`: SHA-1 HMAC hex digest signed using the secret key over the request datetime string.

### Key Workflows & Features

1. **Supported Record Types**: `A`, `AAAA`, `ALIAS` (mapped to DNS Made Easy `ANAME`), `CAA`, `CNAME`, `MX`, `NS`, `PTR`, `SRV`, `TXT`.
2. **Sandbox Environment**: Supports setting `sandbox=True` during initialization to route API requests to `https://api.sandbox.dnsmadeeasy.com/V2.0/dns/managed` instead of production.
3. **Throttling Delay**: Configures `ratelimit_delay` (float) to pause execution between requests to prevent API rate-limit exhaustion.
4. **Dynamic Routing**: Not supported (`SUPPORTS_DYNAMIC=False`, `SUPPORTS_GEO=False`).
5. **Dynamic Subnets**: Not supported (`SUPPORTS_DYNAMIC_SUBNETS=False`).
6. **Pool Value Status**: Not supported (`SUPPORTS_POOL_VALUE_STATUS=False`).

## Development & Testing

- **Setup Script**: Run `./script/bootstrap` to create a virtual environment, install dependencies (including `black`, `isort`, `pyflakes`, and `pytest`), and configure pre-commit hooks.
- **Test Suite**: Run unit tests using `pytest` via `./script/test` (or `pytest tests/`). Test files are located in [tests/](file:///home/ross/octodns/octodns-dnsmadeeasy/tests).
- **Code Coverage**: Verify code coverage using `./script/coverage`.

## Key Constraints & Behaviors

- **Python Version**: Targets Python `>=3.9`.
- **Formatting**: Code formatting is enforced via `black` (version `>=26.0.0,<27.0.0`) and `isort`.
