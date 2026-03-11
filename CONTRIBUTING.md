# Contributing

Issues and PRs welcome! This project follows the Unix philosophy: do one thing well.

## Running Tests Locally

```bash
# Run the full demo (requires jj + git)
bash examples/two-agents-demo/run.sh

# Run the minimal hello-world example
bash examples/hello-world/run.sh
```

The CI workflow runs the same tests automatically on every push — see [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Code Style

- Shell scripts: use `set -euo pipefail`, quote variables, prefer `local` in functions
- JSON: 2-space indent, follow the schema in [spec/PROTOCOL.md](spec/PROTOCOL.md)

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Test locally with the demo script
4. Open a PR with a clear description of what changed and why
