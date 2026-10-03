# Right-Click New

**The Windows "New" menu for Linux.** Right-click in a folder or on the
desktop and create a blank Word, Excel or PowerPoint file, a drawing, a text
file, a notebook or a shortcut, the way you would on Windows.

Built for Ubuntu's GNOME Files (Nautilus) and desktop. The templates also
work in Nemo, Caja, Thunar and Dolphin.

```
Right-click in a Files window or on the desktop
├── New Folder                             built in
├── New Document ▸                         from your Templates folder
│   ├── Microsoft Excel Worksheet          .xlsx     Sheet1
│   ├── Microsoft PowerPoint Presentation  .pptx     16:9, title slide + 4 layouts
│   ├── Microsoft Word Document            .docx     Letter (or A4), Calibri 11
│   ├── Pinta Image                        .ora      1920×1080 canvas, opens in Pinta
│   ├── SQLite Database                    .sqlite3  stands in for Access
│   ├── Text Document                      .txt
│   └── extras: CSV File, Jupyter Notebook, Markdown Document, Python Script,
│               Quarto Document, R Markdown Document, R Script
└── New Shortcut…                          Files windows only (extension)
```

The Office files are real, valid Office Open XML documents (not empty
placeholders), checked by opening them in LibreOffice and with the
python-docx / openpyxl / python-pptx readers. Word files carry the modern
compatibility flag, so Word won't open them in Compatibility Mode.

## Install

```bash
git clone https://github.com/melhzy/right-click-new.git
cd right-click-new
./install.sh --with-deps        # also apt-installs python3-nautilus, zenity, pinta
nautilus -q                     # reload Files so "New Shortcut…" appears
```

Templates appear immediately; only the shortcut item needs the Files restart.
To update later: `git pull && ./install.sh` (it only replaces templates it
installed and you haven't edited).

| Option | Effect |
|---|---|
| `--no-extras` | Only the Windows items, no Python/R/data templates |
| `--group-extras` | Put the extras in a **Code and Data ▸** submenu |
| `--paper a4` | A4 Word template (default Letter) |
| `--canvas-size 1280x720` | Different Pinta Image canvas size |
| `--no-shortcut` | Skip the **New Shortcut…** extension |
| `--force` | Replace same-named files already in Templates (backed up first) |
| `--restart-files` | Run `nautilus -q` for you |

Re-run `./install.sh` with different options at any time; it only touches
files it created, and removes ones you deselect.

## Uninstall

```bash
./uninstall.sh            # keeps any template you edited
./uninstall.sh --force    # removes those too (a copy goes to ~/.local/share/right-click-new/backup)
```

## How it works

* **Templates.** Files and the desktop build **New Document ▸** from the
  folder registered as `XDG_TEMPLATES_DIR` (normally `~/Templates`). The
  menu label is the file name without its extension. `build_templates.py`
  finds that folder (re-enabling it if it was disabled), writes the
  templates, and records them in `~/.local/share/right-click-new/manifest.json`.
  It uses only the Python standard library.
* **New Shortcut…** A `nautilus-python` extension adds the item to the
  folder-background menu. It opens a small dialog (zenity):
  * a **file or folder** becomes a symbolic link (the file's extension is
    kept so it opens in the right app; name clashes get ` (2)` like Windows);
  * a **web address** becomes a tiny `.html` file that opens the address in
    your browser. It works from Files, the desktop, and other computers.
  You can also run it from a terminal:
  `~/.local/share/right-click-new/new-shortcut ~/Desktop --url scholar.google.com`
* **Pinta Image.** Ubuntu has no Paint-style app, so the drawing template
  is a blank canvas in OpenRaster (`.ora`), the layered format Pinta saves
  natively, the way `.docx` belongs to a word processor. The installer makes
  Pinta the app for `.ora` files (uninstall restores whatever had them
  before); your PNG/JPEG photos, plots and screenshots keep opening in Image
  Viewer. Double-click a Pinta Image to draw; **Ctrl+S** keeps it as `.ora`
  (layers intact) and **File ▸ Save As** exports PNG or JPEG.

## Differences from Windows

* GNOME keeps **New Folder** and **New Document ▸** as separate items, and
  the menu shows no per-type icons (GTK 4 popover menus don't display them).
* A new file is named after its template (`Microsoft Word Document.docx`);
  Windows adds a "New " prefix. Rename it as usual (F2).
* **New Shortcut…** appears in Files windows only. Ubuntu's desktop icons
  come from a separate GNOME Shell extension with its own menu, which
  doesn't load Files extensions (New Document ▸ does work there).
* **Bitmap image** becomes **Pinta Image** (`.ora`), so a new drawing opens
  straight in an editor instead of an image viewer.
* Access, Project and Publisher have no direct Linux equivalents. Access is
  replaced by SQLite; Project and Publisher are left out.

## Troubleshooting

**`ImportError: ... No module named 'gi'` / `pygobject initialization failed`**
when you run `nautilus` from a terminal: a conda environment (even `(base)`)
or a venv is active. Files' built-in Python follows your `PATH`, picks up
that environment's Python, and can't find the system `gi` module. Nothing
is broken: open Files from the dock or Activities instead, or run
`conda deactivate` before starting `nautilus` from the terminal.

**A Pinta Image opens in something other than Pinta** (e.g. GIMP or an
archive manager): run `./install.sh` again, or right-click the file ▸
**Open With…** ▸ Pinta ▸ **Always use for this file type**.

**New Shortcut… doesn't appear:** check that `python3-nautilus` and
`zenity` are installed, run `nautilus -q`, then open Files from the dock.
The item only shows on the background of a local folder you can write to
(not in Trash, network locations or read-only folders).

## Adding your own

Drop any file into `~/Templates` and it appears in the menu, e.g. a lab
report `.docx` with your header, or an analysis notebook with your usual
imports. To add one to the generator itself, add a `Template(...)` line to
the `TEMPLATES` list in `build_templates.py`.

## Files

| File | Purpose |
|---|---|
| `install.sh` / `uninstall.sh` | Entry points |
| `build_templates.py` | Generates and manages the templates (`install`, `uninstall`, `list`, `build DIR`) |
| `bin/new-shortcut` | Shortcut dialog and link creation |
| `nautilus/right_click_new.py` | Files extension (Nautilus API 4.x, falls back to 3.0) |
| `tests/` | Template validation, install/uninstall, shortcut and extension tests |

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r tests/requirements.txt
tests/run_all.sh
```

`run_all.sh` lints the Python and shell code, validates every template with
independent readers (plus LibreOffice when it's installed), and runs the
install/uninstall, shortcut and extension tests in a throwaway home folder,
so it never touches your real `~/Templates`. GitHub Actions runs the same
script on Python 3.10, 3.12 and 3.13.

## License

MIT
