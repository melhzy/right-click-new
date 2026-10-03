#!/usr/bin/env python3
"""Exercise nautilus/right_click_new.py against stubbed gi modules,
for both the Nautilus 4.x API and the 3.0 fallback."""
import importlib.util
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class MenuItem:
    def __init__(self, **props):
        self.props = props
        self.callback = None

    def connect(self, _signal, callback, *data):
        self.callback = (callback, data)


class Folder:
    def __init__(self, path):
        self.path = path

    def get_location(self):
        return types.SimpleNamespace(get_path=lambda: self.path)


def load_extension(has_api4: bool, launched: dict):
    def require_version(_ns, version):
        if version == "4.0" and not has_api4:
            raise ValueError("Namespace Nautilus not available for version 4.0")

    class Subprocess:
        @staticmethod
        def new(argv, _flags):
            launched["argv"] = argv

    gi = types.ModuleType("gi")
    gi.require_version = require_version
    repo = types.ModuleType("gi.repository")
    repo.GObject = types.SimpleNamespace(GObject=type("GObject", (), {}))
    repo.Nautilus = types.SimpleNamespace(
        MenuProvider=type("MenuProvider", (), {}), MenuItem=MenuItem)
    repo.Gio = types.SimpleNamespace(
        Subprocess=Subprocess, SubprocessFlags=types.SimpleNamespace(NONE=0))
    sys.modules.update({"gi": gi, "gi.repository": repo})
    spec = importlib.util.spec_from_file_location(
        "right_click_new", ROOT / "nautilus" / "right_click_new.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    home = Path(tempfile.mkdtemp())
    helper = home / ".local/share/right-click-new/new-shortcut"
    helper.parent.mkdir(parents=True)
    helper.write_text("#")
    os.environ["HOME"] = str(home)
    os.environ.pop("XDG_DATA_HOME", None)
    fake_bin = home / "bin"
    fake_bin.mkdir()
    (fake_bin / "zenity").write_text("#!/bin/sh\n")
    (fake_bin / "zenity").chmod(0o755)
    os.environ["PATH"] = f"{fake_bin}:{os.environ['PATH']}"

    failures = 0
    for has_api4, label, call in (
        (True, "API 4.x", lambda p, f: p.get_background_items(f)),
        (False, "API 3.0", lambda p, f: p.get_background_items(object(), f)),
    ):
        launched: dict = {}
        ext = load_extension(has_api4, launched)
        provider = ext.RightClickNew()
        items = call(provider, Folder(str(home)))
        remote = call(provider, Folder(None))          # sftp://, trash://, ...
        missing = call(provider, Folder(str(home / "nope")))
        ok = (len(items) == 1 and items[0].props["label"] == "New Shortcut…"
              and remote == [] and missing == [])
        if ok:
            callback, data = items[0].callback
            callback(items[0], *data)
            ok = launched.get("argv", [None])[1:] == [str(helper), str(home)]
        print(f"{'PASS' if ok else 'FAIL'}  extension ({label}): item shown for local "
              "folders, hidden for remote/missing, launches helper")
        failures += not ok
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
