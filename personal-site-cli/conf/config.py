import yaml


class Config:
    def __init__(self, path: str):
        with open(path, "r") as yaml_config_file:
            self.config = yaml.safe_load(yaml_config_file)

    def __getattr__(self, name):
        try:
            return self.config[name]
        except KeyError:
            return getattr(self.args, name)
