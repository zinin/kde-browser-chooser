"""Runs a function in a child process, so that a crash there is an exception here.

Qt aborts when it cannot open the display, and a crash in C++ cannot be caught
either; in both cases the link must not be lost. The child also takes all traces
of Qt with it: the parent becomes the browser without them.
"""
import ctypes
import json
import os
import signal
from collections.abc import Callable
from typing import Any, NoReturn

from .log import log_exception

PR_SET_PDEATHSIG = 1


class Crashed(Exception):
    """The child process ended without an answer."""


def run(function: Callable, *args) -> Any:
    """Returns what function(*args) returned, as JSON carries it."""
    read_end, write_end = os.pipe()
    parent = os.getpid()
    pid = os.fork()
    if pid == 0:
        _answer(parent, read_end, write_end, function, args)
    os.close(write_end)
    with open(read_end, "rb") as pipe:
        answer = pipe.read()
    _, status = os.waitpid(pid, 0)
    if status or not answer:
        raise Crashed(f"the child process ended with {os.waitstatus_to_exitcode(status)}")
    return json.loads(answer)


def _answer(parent: int, read_end: int, write_end: int, function: Callable, args: tuple) -> NoReturn:
    status = 1
    try:
        os.close(read_end)
        ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)  # it must not outlive the parent
        if os.getppid() != parent:  # the parent died before prctl, and no signal will come
            os._exit(1)
        with open(write_end, "wb") as pipe:
            pipe.write(json.dumps(function(*args)).encode())
        status = 0
    except BaseException:
        log_exception()
    finally:
        os._exit(status)
