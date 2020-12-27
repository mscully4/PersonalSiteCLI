from dataclasses import dataclass, asdict
import math
from pyfiglet import Figlet
import os
import readline


def print_figlet(text):
    cls()
    print(Figlet(font="slant").renderText(text))


def print_menu(app_name):
    cls()

    print_figlet(app_name)
    print("Main Menu")

    print("0. To Exit")
    print("1. Enter a new destination")
    print("2. Enter a new place")
    print("3. Add an album to a place")
    print("4. Edit a destination")
    print("5. Edit a place")
    print("6. Delete a destination")
    print("7. Delete a place")
    print("8. Add Photos")
    print("9. Add Album Cover")

    print()


def print_single_list(sugs):
    print("Enter < to go back")
    for i, sug in enumerate(sugs):
        print(f"{i+1}. {sug}")


def print_double_list(lst):
    half = math.ceil(len(lst) / 2)

    print("Enter < to go back")
    for i in range(half):
        print("{0: <50}".format(str(i + 1) + ". " + lst[i].name), end="")
        if i + half + 1 <= len(lst):
            print("{0}".format(str(i + half + 1) + ". " + lst[i + half].name))
        else:
            print()


def get_selection(minimum, maximum, allowed_chars="/<*"):
    selection = input("Selection: ")

    if selection in allowed_chars:
        return selection

    selection = try_cast(selection, int)
    assert selection != None
    assert minimum <= selection <= maximum

    return selection


def get_input(msg, default=None):
    print(msg)
    if default:
        return rlinput("Input: ", default)

    return input("Input: ")


def ask_yes_no_question(text):
    return input(text).lower() in ("y", "yes")


def edit_obj(obj):
    """
    Editing the information of a destination in the dictionary

    Args:
        override_destination::[int]
            the ID of the destination containing the place.  If not specified, the user will be prompted to select a destination

    Returns:
        None
    """
    items = obj.asdict()
    for k, v in items.items():
        inp = rlinput("{}: ".format(k), str(v))

        inp_as_float = try_cast(inp, float)
        if inp_as_float != None:
            # If the input is a number, save it as a float or int
            items[k] = inp_as_float if "." in inp else int(inp)
            # if the input is a string, save it as such
        elif isinstance(v, str):
            items[k] = inp

    return obj.__class__(**items)


def cls():
    os.system("cls" if os.name == "nt" else "clear")


def clr_line():
    print("\033[A                             \033[A")


def try_cast(val, type_):
    try:
        return type_(val)
    except Exception as e:
        return None


def rlinput(prompt, prefill=""):
    readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(prompt)
    finally:
        readline.set_startup_hook()
