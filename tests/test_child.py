import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kde_browser_chooser import child

SRC = Path(__file__).resolve().parent.parent / "src"


def test_result_and_arguments():
    assert child.run(lambda a, b: [b, a, None], "x", 1) == [1, "x", None]


def test_big_and_odd_results():
    assert child.run(lambda: ["x" * 1_000_000, "\udcff"]) == ["x" * 1_000_000, "\udcff"]


def test_it_is_another_process():
    assert child.run(os.getpid) != os.getpid()


def fail():
    raise ValueError("inside")


@pytest.mark.parametrize("function", [
    fail, lambda: os.kill(os.getpid(), signal.SIGKILL), lambda: os._exit(0), lambda: os._exit(3), lambda: sys.exit(0)],
    ids=["exception", "signal", "silent exit", "exit 3", "sys.exit"])
def test_crash_is_an_exception(function):
    with pytest.raises(child.Crashed):
        child.run(function)


def test_child_does_not_outlive_the_parent(tmp_path):
    pid_file = tmp_path / "pid"
    code = (f"import os, sys, time; sys.path.insert(0, {str(SRC)!r})\nfrom kde_browser_chooser import child\n"
            f"def f():\n    open({str(pid_file)!r} + '.part', 'w').write(str(os.getpid()))\n"
            f"    os.rename({str(pid_file)!r} + '.part', {str(pid_file)!r})\n    time.sleep(60)\nchild.run(f)")
    parent = subprocess.Popen([sys.executable, "-B", "-c", code])
    deadline = time.monotonic() + 10
    while not pid_file.exists():
        assert time.monotonic() < deadline
        time.sleep(0.02)
    parent.kill()
    parent.wait()
    while Path("/proc", pid_file.read_text()).exists():
        assert time.monotonic() < deadline, "the child is still there"
        time.sleep(0.02)
