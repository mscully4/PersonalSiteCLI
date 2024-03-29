import math
import os
import readline
from typing import Any, List
from attrs import asdict
from pyfiglet import Figlet
from utils.navigation import (
    MenuNavigationCodes,
    menuNavigationUserCommandsToCodes,
)


def print_figlet(text: str) -> None:
    cls()
    print(Figlet(font="slant").renderText(text))


def print_single_list(sugs: List[str]) -> None:
    print("Enter < to go back")
    for i, sug in enumerate(sugs):
        print(f"{i+1}. {sug}")


def print_double_list(lst: List[Any]) -> None:
    half = math.ceil(len(lst) / 2)

    print("Enter < to go back")
    for i in range(half):
        print("{0: <50}".format(str(i + 1) + ". " + lst[i].name), end="")
        if i + half + 1 <= len(lst):
            print("{0}".format(str(i + half + 1) + ". " + lst[i + half].name))
        else:
            print()


def get_selection(
    minimum: int,
    maximum: int,
    allowed_chars: List[str],
) -> int:
    """
    A function for getting a numerical selection from a user. If the selection
    is valid it will be returned, otherwise -1 will be returned
    """
    selection = input("Selection: ")

    if selection in allowed_chars:
        return menuNavigationUserCommandsToCodes.get(selection, MenuNavigationCodes.INVALID_INPUT)

    if selection in menuNavigationUserCommandsToCodes:
        return MenuNavigationCodes.FORBIDDEN_INPUT

    try:
        selection_as_int = int(selection)
    except ValueError:
        return MenuNavigationCodes.INVALID_INPUT

    if not (minimum <= selection_as_int <= maximum):
        return MenuNavigationCodes.INPUT_OUT_OF_RANGE

    return selection_as_int


def get_input(msg: str = "Input", default: str = None) -> str:
    """
    Prompts the user for input and returns that input
    """
    if default:
        return rlinput(f"{msg}: ", default)

    return input(f"{msg}: ")


def ask_yes_no_question(text: str) -> bool:
    """
    Prompts the user to answer a provided question and then checks if the
    response is y/yes
    """
    return input(text).lower() in ("y", "yes")


def edit_obj(obj: Any) -> Any:
    """
    Edits the information of a destination in the dictionary
    """
    items = asdict(obj)
    for k, v in items.items():
        inp = rlinput("{}: ".format(k), str(v))

        try:
            inp_as_float = float(inp)
            items[k] = inp_as_float if "." in inp else int(inp)
        except ValueError:
            if isinstance(v, str):
                items[k] = inp

    return obj.__class__(**items)


def cls() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def clr_line() -> None:
    print("\033[A                             \033[A")


def rlinput(prompt, prefill: str = "") -> str:
    readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()
