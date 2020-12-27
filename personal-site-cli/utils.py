import os
import readline 

def cls():
    os.system('cls' if os.name=='nt' else 'clear')

def clr_line():
    print("\033[A                             \033[A")

def try_cast(val, type_):
    try:
        return type_(val)
    except Exception as e: 
        return None

def rlinput(prompt, prefill=''):
   readline.set_startup_hook(lambda: readline.insert_text(prefill))
   try:
      return input(prompt)  # or raw_input in Python 2
   finally:
      readline.set_startup_hook()