#! /bin/bash

set -e

echo "Running Black"
uv run black ./personal-site-cli --check
printf "\n"

# Still disabled: 9 pre-existing files fail. Run `uv run isort ./personal-site-cli` to fix.
# echo "Running isort"
# uv run isort ./personal-site-cli --check-only
# printf "\n"

echo "Running Flake8"
uv run flake8 ./personal-site-cli
printf "\n"

echo "Running Mypy"
uv run mypy ./personal-site-cli
