import contextlib
import traceback


def log_exception() -> None:
    with contextlib.suppress(Exception):  # stderr may be closed, and the link must open anyway
        traceback.print_exc()
