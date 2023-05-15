import numpy as np

THREADS = 8


def split(lst, n):
    return np.array_split(lst, n)
