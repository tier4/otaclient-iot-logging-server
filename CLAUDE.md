# CLAUDE.md

## Project Overview

`otaclient-iot-logging-server` is a Python-based logging server that receives logs from otaclient and uploads them to AWS CloudWatch via AWS IoT/Greengrass.

## Development Environment

- **Python**: 3.10+
- **Package manager**: `uv` (not pip/poetry)
- **Build backend**: hatchling with hatch-vcs (version from git tags)

## Common Commands

```bash
# Setup
uv sync --locked

# Run tests
uv run pytest

# Run tests with coverage
uv run coverage run -m pytest && uv run coverage report

# Lint/format (via pre-commit)
uv run pre-commit run --all-files

# Build wheel
uv build --wheel
```

## Project Structure

```text
src/otaclient_iot_logging_server/  # Main package
tests/                              # Test files
proto/                              # gRPC proto definitions
examples/                           # Example configuration files
tools/                              # Development tools
```

## Code Quality

- **Linter/formatter**: ruff (configured in `pyproject.toml`)
- **Pre-commit hooks**: end-of-file-fixer, trailing-whitespace, ruff, ruff-format, pyproject-fmt, markdownlint
- Auto-generated protobuf files (`*_pb2.py`, `*_pb2_grpc.py`) are excluded from linting

## Key Architecture Notes

- Supports Greengrass v1 and v2 configs (v2 takes precedence if both exist)
- Optionally filters logs by known ECU IDs from `ecu_info.yaml`
- Supports TPM/pkcs11 for Greengrass certificate handling
- gRPC server on port 8084, HTTP proxy on port 8083
- Restarts on config file changes (designed for use with systemd `Restart` policy)

## Testing

- Framework: pytest with pytest-asyncio (`asyncio_mode = auto`)
- Test env vars are set via `pytest-env` (see `[tool.pytest]` in `pyproject.toml`)
- Test data lives in `tests/data/`
