"""
Right-Click New - GNOME Files (Nautilus) extension: adds "New Shortcut…"
to the right-click menu of a folder's background, like Windows' New > Shortcut.

Requires the python3-nautilus package. Works with the Nautilus 4.x
extension API (Ubuntu 22.10 and later) and the 3.0 API (Ubuntu 22.04).
Install to ~/.local/share/nautilus-python/extensions/ and run `nautilus -q`.
"""

import os
import shutil
from pathlib import Path

import gi

for _version in ("4.0", "3.0"):
    try:
        gi.require_version("Nautilus", _version)
        break
    except ValueError:
        continue

from gi.repository import GObject, Gio, Nautilus  # noqa: E402

_DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
HELPER = Path(_DATA_HOME) / "right-click-new" / "new-shortcut"
# The system interpreter: the helper needs only the standard library, and
# this avoids picking up a conda/venv python that happens to be on PATH.
PYTHON = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"


class RightClickNew(GObject.GObject, Nautilus.MenuProvider):
    """Background-menu provider."""

    def get_background_items(self, *args):
        # API 4.x passes (folder); API 3.0 passes (window, folder).
        folder = args[-1] if args else None
        path = _local_path(folder)
        if not path or not os.access(path, os.W_OK):
            return []
        if not HELPER.is_file() or shutil.which("zenity") is None:
            return []
        item = Nautilus.MenuItem(
            name="RightClickNew::new_shortcut",
            label="New Shortcut…",
            tip="Create a shortcut to a file, folder or web address here",
        )
        item.connect("activate", self._on_activate, path)
        return [item]

    def get_file_items(self, *args):
        return []

    @staticmethod
    def _on_activate(_item, path):
        # Gio.Subprocess is reaped by GLib, so no zombie processes are left.
        Gio.Subprocess.new([PYTHON, str(HELPER), path], Gio.SubprocessFlags.NONE)


def _local_path(folder):
    """Return the local path of a Nautilus folder, or None (e.g. SFTP, trash)."""
    if folder is None:
        return None
    try:
        location = folder.get_location()
    except AttributeError:
        return None
    return location.get_path() if location is not None else None
