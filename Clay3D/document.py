"""The open document: unsaved changes, saving, and crash recovery. Mixin on EditorWindow.

- Any edit marks the document unsaved; New, Open and closing the window ask
  "Do you want to save your work?" first.
- Save writes back to the file the document came from; the first save asks where.
- Every write goes to a temporary file that replaces the target only once it
  is complete, and a failure says so instead of passing silently.
- While there are unsaved changes, a copy is written to the recovery folder
  every AUTOSAVE_SECONDS. It is removed when the work is saved or discarded,
  so anything left there after a crash shows under Menu > Open > Recovered projects.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from Clay3D import recent
from Clay3D.canvas2d import Canvas
from Clay3D.io_files import IMAGE_SUFFIXES, save_image, save_scene
from Clay3D.scene3d import Scene

AUTOSAVE_SECONDS = 60
RECOVERY_KEEP = 8
UNTITLED = "Untitled"
SAVE_FILTERS = "Clay3D project (*.clay3d);;PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)"
AUTOSAVER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clay3d-autosave")


def recovery_dir() -> Path:
    # CLAY3D_RECOVERY_DIR keeps tests away from the real folder.
    override = os.environ.get("CLAY3D_RECOVERY_DIR")
    if override:
        folder = Path(override)
    else:
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        folder = Path(base or Path.home() / ".local/share/Clay3D") / "recovered"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def recovered_projects() -> list[Path]:
    """Recovery files left by sessions that ended without saving, newest first."""
    files = sorted(recovery_dir().glob("*.clay3d"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[RECOVERY_KEEP:]:
        stale.unlink(missing_ok=True)
    return files[:RECOVERY_KEEP]


def write_atomically(path: str | Path, write) -> None:
    """Run write(temp_path), then move the finished file over path."""
    path = Path(path)
    handle, temp = tempfile.mkstemp(prefix=".clay3d-", suffix=path.suffix, dir=path.parent)
    os.close(handle)
    try:
        write(temp)
        # mkstemp files are owner-only; keep the old file's mode, or the usual default.
        if path.exists():
            mode = path.stat().st_mode & 0o7777
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def snapshot_scene(scene: Scene) -> Scene:
    """A copy the autosave thread can write while editing carries on."""
    canvas = Canvas(scene.canvas.width, scene.canvas.height, background=scene.canvas.background)
    canvas.pixels = scene.canvas.pixels.copy()
    copy = Scene(canvas=canvas)
    copy.objects = [obj.copy() for obj in scene.objects]
    copy.selected_index = scene.selected_index
    copy.camera = scene.camera.copy()
    copy.show_canvas = scene.show_canvas
    copy.effect = scene.effect
    copy.light_rotation = scene.light_rotation
    return copy


class DocumentActions:
    """Document lifecycle for `EditorWindow`."""

    def init_document(self) -> None:
        self.document_path: str | None = None
        self.unsaved = False
        self.recovery_path = recovery_dir() / f"session-{uuid.uuid4().hex[:8]}.clay3d"
        self._autosave_job = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_SECONDS * 1000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()
        self._update_title()

    # ---- state -----------------------------------------------------------------

    def document_name(self) -> str:
        return Path(self.document_path).name if self.document_path else UNTITLED

    def mark_unsaved(self) -> None:
        if not self.unsaved:
            self.unsaved = True
            self._update_title()

    def mark_saved(self, path: str | None) -> None:
        self.document_path = path
        self.unsaved = False
        self._discard_recovery()
        self._update_title()

    def _update_title(self) -> None:
        marker = "*" if self.unsaved else ""
        self.setWindowTitle(f"{self.document_name()}{marker} - Clay3D")

    # ---- asking ------------------------------------------------------------------

    def ask_to_save(self) -> str:
        """'save', 'discard' or 'cancel'. Tests replace this."""
        box = QMessageBox(self)
        box.setWindowTitle("Clay3D")
        box.setText("Do you want to save your work?")
        box.setInformativeText(f"There are unsaved changes to {self.document_name()}.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        if clicked is discard:
            return "discard"
        return "cancel"

    def confirm_leaving_document(self) -> bool:
        """True when it is fine to replace or close the current document."""
        if not self.unsaved:
            return True
        choice = self.ask_to_save()
        if choice == "save":
            return self.save_document()
        if choice == "discard":
            self._discard_recovery()
            return True
        return False

    def handle_close(self, event) -> None:
        """Window close: EditorWindow.closeEvent forwards here (QMainWindow's own comes first in the MRO)."""
        if self.confirm_leaving_document():
            self._autosave_timer.stop()
            event.accept()
        else:
            event.ignore()

    # ---- saving ------------------------------------------------------------------

    def save_document(self) -> bool:
        """Menu > Save: back to the document's own file, or ask where the first time."""
        if self.document_path is None:
            return self.save_document_as()
        return self.write_document(self.document_path)

    def save_document_as(self) -> bool:
        path, chosen = QFileDialog.getSaveFileName(
            self, "Save", f"{Path(self.document_name()).stem}.clay3d", SAVE_FILTERS
        )
        if not path:
            return False
        if Path(path).suffix.lower() not in IMAGE_SUFFIXES | {".clay3d"}:
            # No extension typed: use the file type picked in the dialog.
            picked = chosen.split("*", 1)[1].rstrip(")") if "*" in chosen else ".clay3d"
            path += picked
        return self.write_document(path)

    def write_document(self, path: str) -> bool:
        """Write the whole document to path; the format follows the extension."""
        self.clear_selection()
        self.commit_live_shape()
        self.commit_text_box()
        if path.lower().endswith(".clay3d"):
            written = self.write_file(path, lambda temp: save_scene(self.scene, temp))
        else:
            written = self.write_file(path, lambda temp: save_image(self.canvas, temp))
        if written:
            recent.remember(path)
            self.mark_saved(path)
            self.hide_menu()
        return written

    def write_file(self, path: str, write) -> bool:
        """Write through a temporary file; on failure say so and return False."""
        try:
            write_atomically(path, write)
            return True
        except (OSError, ValueError) as error:
            self.report_save_failure(error)
            return False

    def report_save_failure(self, error: Exception) -> None:
        self.save_error = str(error)
        if getattr(self, "suppress_dialogs", False):
            return
        detail = getattr(error, "strerror", None) or str(error) or "Something went wrong."
        QMessageBox.warning(self, "Couldn’t save", detail)

    # ---- recovery -----------------------------------------------------------------

    def autosave(self) -> None:
        """Copy the unsaved document to the recovery folder, off the UI thread."""
        if not self.unsaved:
            return
        if self._autosave_job is not None and not self._autosave_job.done():
            return
        scene = snapshot_scene(self.scene)
        target = self.recovery_path
        self._autosave_job = AUTOSAVER.submit(write_atomically, target, lambda temp: save_scene(scene, temp))

    def wait_for_autosave(self) -> None:
        if self._autosave_job is not None:
            self._autosave_job.result()

    def _discard_recovery(self) -> None:
        self.wait_for_autosave()
        self.recovery_path.unlink(missing_ok=True)

    def open_recovered(self, path: str) -> None:
        """Open a recovered project as unsaved work, and adopt its recovery file."""
        if not self.confirm_leaving_document():
            return
        if not self.load_document(path):
            return
        self._discard_recovery()
        self.recovery_path = Path(path)
        self.document_path = None
        self.unsaved = True
        self._update_title()

    def recovered_age(self, path: Path) -> str:
        minutes = int((time.time() - path.stat().st_mtime) // 60)
        if minutes < 60:
            return f"{minutes} min ago"
        if minutes < 60 * 24:
            return f"{minutes // 60} h ago"
        return f"{minutes // (60 * 24)} days ago"
