#! /bin/bash

set -e

echo "Running Black"
black ./personal-site-cli --check
printf "\n"

# echo "Running isort"
# (cd ./personal-site-cli && python3 -m isort --check-only --recursive .)
# printf "\n"

echo "Running Flake8"
flake8 ./personal-site-cli
printf "\n"

echo "Running Mypy"
mypy ./personal-site-cli
