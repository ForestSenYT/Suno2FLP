# Run from the repository root after uv sync. Stop on the first failed check.
$ErrorActionPreference = 'Stop'
uv run --locked ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run --locked ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run --locked mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run --locked pytest
exit $LASTEXITCODE
