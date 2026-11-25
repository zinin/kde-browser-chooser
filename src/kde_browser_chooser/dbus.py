"""Calls D-Bus methods with a command-line tool, because PyQt6 may be missing."""
from .process import succeeds


def gvariant(kind: str, value: str) -> str:
    match kind:
        case "s":
            return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
        case "u":
            return f"uint32 {value}"
        case "i":
            return f"int32 {value}"
        case "as":
            return "@as []"
        case "a{sv}":
            return "@a{sv} {}"
    raise ValueError(kind)


def call(service: str, path: str, interface: str, method: str, *args: tuple[str, str]) -> bool:
    """Arguments are (type, value) pairs; arrays and dictionaries are always empty."""
    signature = ["".join(kind for kind, _ in args)] if args else []
    values = ["0" if kind.startswith("a") else value for kind, value in args]
    return (
        succeeds(["busctl", "--user", "--", "call", service, path, interface, method, *signature, *values])
        or succeeds(["gdbus", "call", "--session", "--dest", service, "--object-path", path,
                     "--method", f"{interface}.{method}", "--", *(gvariant(*arg) for arg in args)])
    )
