"""strip_token.py IN OUT copies the program without its request for a fresh token: the bench must notice."""
import sys
import zipfile

source, target = sys.argv[1:]
old, new = b"request_token(window, window.accept)", b"window.accept()"
with zipfile.ZipFile(source) as archive, open(target, "wb") as file:
    file.write(b"#!/usr/bin/python3 -I\n")
    with zipfile.ZipFile(file, "w") as copy:
        for name in archive.namelist():
            data = archive.read(name)
            if name.endswith("/window.py"):
                assert data.count(old) == 1
                data = data.replace(old, new)
            copy.writestr(name, data)
