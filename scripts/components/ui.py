#!/usr/bin/env python3
# Utility functions for command line UI
from __future__ import print_function
from colorama import Style
import sys
import threading
import time

# input() in Python 3, raw_input() in Python 2
try:
    # noinspection PyUnresolvedReferences,PyShadowingBuiltins
    input = raw_input
except NameError:
    pass


class Spinner:
    spinning = False
    delay = 0.25

    @staticmethod
    def spinning_cursor():
        while 1:
            for cursor in '|/-\\':
                yield cursor

    def __init__(self, delay=None):
        self.spinner_generator = self.spinning_cursor()
        if delay and float(delay):
            self.delay = delay

    def spinner_task(self):
        while self.spinning:
            sys.stdout.write(next(self.spinner_generator))
            sys.stdout.flush()
            time.sleep(self.delay)
            sys.stdout.write('\b')
            sys.stdout.flush()

    def start(self):
        self.spinning = True
        threading.Thread(target=self.spinner_task).start()

    def stop(self):
        self.spinning = False
        time.sleep(self.delay)


def cprint(*pargs, **kwargs):
    """
    Print a string to the terminal with colour

    :param pargs: args to print()
    :param kwargs: kwargs to print()
    """
    if 'colour' in kwargs:
        print(kwargs['colour'], end="")
        del kwargs['colour']

        end = kwargs.get('end', '\n')
        kwargs['end'] = ''
        print(*pargs, **kwargs)

        print(Style.RESET_ALL, end=end)

    else:
        print(*pargs, **kwargs)


def confirm(question='', count=0):
    reply = str(input(question)).lower().strip()
    if reply[:1] == 'y':
        return True
    if reply[:1] == 'n' or count >= 3:
        return False
    else:
        return confirm('Please type "yes" or "no": ', count + 1)
