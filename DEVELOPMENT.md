# Development Guide

This document describes how to set up a development environment for otaclient-iot-logging-server.

## Prerequisites

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager

## Setup

1. Install `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

1. Clone the repository and set up the development environment:

   ```bash
   git clone https://github.com/tier4/otaclient-iot-logging-server.git
   cd otaclient-iot-logging-server
   uv sync --locked
   ```

1. Install pre-commit hooks:

   ```bash
   uv run pre-commit install
   ```

## Running Tests

Run all tests:

```bash
uv run pytest
```

Run tests with coverage:

```bash
uv run coverage run -m pytest
uv run coverage report
```

## Building

Build the wheel package:

```bash
uv build --wheel
```

The built package will be placed under `./dist` folder.

## Code Quality

This project uses the following tools for code quality:

- **ruff**: Linting and formatting
- **pyproject-fmt**: pyproject.toml formatting
- **markdownlint**: Markdown formatting
- **pre-commit**: Git hooks for automated checks

Run all pre-commit checks manually:

```bash
uv run pre-commit run --all-files
```

## Project Structure

```text
├── src/
│   └── otaclient_iot_logging_server/  # Main package
├── tests/                              # Test files
├── proto/                              # gRPC proto definitions
├── examples/                           # Example configuration files
└── tools/                              # Development tools
```
