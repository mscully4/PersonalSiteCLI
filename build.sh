#! /bin/bash

set -e

echo "Running Black"
uv run black ./personal-site-cli ./tests --check
printf "\n"

echo "Running isort"
uv run isort ./personal-site-cli ./tests --check-only
printf "\n"

echo "Running Flake8"
uv run flake8 ./personal-site-cli ./tests
printf "\n"

# Mypy stays on the source only.  The tests lean on fixtures and fakes that
# would need annotating for no benefit
echo "Running Mypy"
uv run mypy ./personal-site-cli
printf "\n"

echo "Running Pytest"
uv run pytest
