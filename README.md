# Clay3D

Paint 3D-inspired 2D/3D editor for Linux.

## Run

```bash
python3 -m Clay3D
```

or use the desktop launcher if you don't want to mess with the command line or set an alias. 

Needs Python 3.11+, NumPy, Pillow, OpenCV,
PySide6, and a GPU with OpenGL 3.3.

## Keyboard

| Key | Action |
|---|---|
| `Ctrl+Z` | Undo |
| `Ctrl+Y` / `Ctrl+Shift+Z` | Redo |
| `Ctrl+N` | New |
| `Ctrl+O` | Open |
| `Ctrl+S` | Save |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copy / cut / paste |
| `Ctrl+A` | Select all |
| `Ctrl+D` | Deselect |
| `Ctrl+Shift+X` | Crop to selection |
| `Ctrl+3` | 2D / 3D view |
| `Ctrl+0` | Fit to window |
| `Ctrl++` / `Ctrl+-` | Zoom |
| `Page Up` / `Page Down` | Zoom |
| `Home` | Reset view |
| `Alt+arrows` | Pan |
| `Ctrl+arrows` | Orbit (3D view) |
| `Space` + drag | Pan |
| `[` / `]` | Brush size |
| `Delete` | Clear selection |
| `Esc` | Cancel (discards text) |
| `Shift+Enter` | Commit text |

## Files

Images open as PNG, JPEG, BMP, WebP, GIF or TIFF, and save as PNG, JPEG, BMP,
GIF or TIFF. Scenes save as `.clay3d` — a zip
holding a JSON manifest beside real PNGs, so a scene file is the size of the
picture in it. 3D objects export to OBJ, PLY, STL and glTF 2.0 - the formats the original
enables in its own settings.

While there are unsaved changes, a copy is written every minute. If Clay3D
closes without saving, the work shows up under Menu > Open > Recovered projects.
Custom stickers are kept between sessions.

Interface icons are [Lucide](https://lucide.dev) (ISC), in `Clay3D/ui_icons/`.
