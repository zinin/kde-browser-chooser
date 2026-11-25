import subprocess

TIMEOUT = 5


def succeeds(argv: list[str], data: bytes = b"") -> bool:
    """Runs a helper program quietly and tells whether it did its job."""
    try:
        return subprocess.run(argv, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=TIMEOUT).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
