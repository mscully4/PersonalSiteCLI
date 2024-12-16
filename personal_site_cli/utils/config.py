import yaml
import os
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]

class Config:
    def __init__(self, path: str):
        with open(path, "r") as yaml_config_file:
            self.config = yaml.safe_load(yaml_config_file)

    def __getattr__(self, name):
        try:
            return self.config[name]
        except KeyError:
            return getattr(self, name)


def get_config() -> Config:
    root_dir = _get_project_root()
    config_path = os.path.join(root_dir, "config.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not locate config file at {config_path}")

    return Config(config_path)

def _get_project_root():
    # Start from the current directory and move upwards
    current_dir = Path(__file__).resolve()
    
    # Loop upwards until we find pyproject.toml
    while current_dir != current_dir.parent:  # Stop when we reach the root
        if (current_dir / 'pyproject.toml').exists():  # Check for pyproject.toml
            return current_dir
        current_dir = current_dir.parent  # Move one directory up
    
    raise FileNotFoundError("pyproject.toml not found in project directory structure.")

