# Project agent guidance

## Graphify

- Before editing code, use the local graph when available to understand the affected symbols, callers, dependencies, and relationships: `.venv-graphify/bin/graphify query "<question>"`. Use `explain` and `path` for focused relationships, then inspect the relevant source before editing.
- For the installed Graphify skill, make its CLI available for the current shell with `export PATH="$PWD/.venv-graphify/bin:$PATH"` from the project root.
- Treat the graph as a navigation aid. Verify relevant source files and use normal searches when the graph is stale, incomplete, or unsuitable for the task.
- After substantial code edits, run `.venv-graphify/bin/graphify update .` from the project root. Report failures rather than claiming the graph was updated.
- The update covers source code locally; documentation and other semantic inputs need a separate explicit semantic update, which can consume tokens. Do not send `.env`, `secrets/`, user data, or private files to external services.
- Installation, output locations, and privacy exclusions are documented in the Graphify section of `README.md`.
