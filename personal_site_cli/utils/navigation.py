from typing import Callable
from attr import field, frozen


@frozen(auto_attribs=True)
class MenuAction:
    name: str
    command: Callable
    is_async: bool = field(default=False)


class MenuNavigationCodes:
    GO_TO_MAIN_MENU = -1
    GO_BACK = -2
    ALL = -9
    INPUT_OUT_OF_RANGE = -77
    INVALID_INPUT = -78
    FORBIDDEN_INPUT = -79


class MenuNavigationUserCommands:
    GO_TO_MAIN_MENU = "/"
    GO_BACK = "<"
    ALL = "*"


menuNavigationUserCommandsToCodes = {
    MenuNavigationUserCommands.GO_BACK: MenuNavigationCodes.GO_BACK,
    MenuNavigationUserCommands.GO_TO_MAIN_MENU: MenuNavigationCodes.GO_TO_MAIN_MENU,
    MenuNavigationUserCommands.ALL: MenuNavigationCodes.ALL,
}
