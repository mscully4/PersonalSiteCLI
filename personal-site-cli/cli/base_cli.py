from abc import ABC, abstractmethod


class BaseCLI(ABC):
    @abstractmethod
    def _print_menu(self):
        pass

    @abstractmethod
    def run(self):
        pass
