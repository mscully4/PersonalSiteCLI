import json
import os
from pathlib import Path

from cattrs import structure

from personal_site_cli.models.auth import Config


def get_config() -> Config:
    root_dir = _get_project_root()
    config_path = os.path.join(root_dir, "config.json")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not locate config file at {config_path}")

    with open(config_path, "r") as fh:
        return structure(json.load(fh), Config)


def _get_project_root():
    # Start from the current directory and move upwards
    current_dir = Path(__file__).resolve()

    # Loop upwards until we find pyproject.toml
    while current_dir != current_dir.parent:  # Stop when we reach the root
        if (current_dir / "pyproject.toml").exists():  # Check for pyproject.toml
            return current_dir
        current_dir = current_dir.parent  # Move one directory up

    raise FileNotFoundError("pyproject.toml not found in project directory structure.")
