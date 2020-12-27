import math
import os
import readline
from typing import Any, List

from pyfiglet import Figlet


def print_figlet(text: str):
    cls()
    print(Figlet(font="slant").renderText(text))


def print_single_list(sugs: List[str]):
    print("Enter < to go back")
    for i, sug in enumerate(sugs):
        print(f"{i+1}. {sug}")


def print_double_list(lst: List[Any]):
    half = math.ceil(len(lst) / 2)

    print("Enter < to go back")
    for i in range(half):
        print("{0: <50}".format(str(i + 1) + ". " + lst[i].name), end="")
        if i + half + 1 <= len(lst):
            print("{0}".format(str(i + half + 1) + ". " + lst[i + half].name))
        else:
            print()


def get_selection(minimum: int, maximum: int, allowed_chars: str = "/<*"):
    """
    A function for getting a numerical selection from a user. If the selection
    is valid it will be returned, otherwise -1 will be returned
    """
    selection = input("Selection: ")

    if selection in allowed_chars:
        return selection

    try:
        selection_as_int = int(selection)
    except ValueError:
        return -1

    if not (minimum <= selection_as_int <= maximum):
        return -1

    return selection_as_int


def get_input(msg: str = "Input", default=None):
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


def edit_obj(obj: Any):
    """
    Edits the information of a destination in the dictionary
    """
    items = obj.asdict()
    for k, v in items.items():
        inp = rlinput("{}: ".format(k), str(v))

        try:
            inp_as_float = float(inp)
            items[k] = inp_as_float if "." in inp else int(inp)
        except ValueError:
            if isinstance(v, str):
                items[k] = inp

    return obj.__class__(**items)


def cls():
    os.system("cls" if os.name == "nt" else "clear")


def clr_line():
    print("\033[A                             \033[A")


def rlinput(prompt, prefill: str = ""):
    readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()
