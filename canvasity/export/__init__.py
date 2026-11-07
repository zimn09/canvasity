"""Image and PDF export of a board."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPageLayout, QPdfWriter

from ..canvas.scene import BoardScene


class ExportError(Exception):
    """Raised when a board cannot be rendered to a file."""


def _prepare_scene(scene: BoardScene, background: QColor) -> tuple[QRectF, QBrush]:
    scene.finish_editing()
    source = scene.content_rect(40.0)
    previous = scene.backgroundBrush()
    scene.setBackgroundBrush(background)
    scene.set_export_mode(True)
    return source, previous


def _finish_scene(scene: BoardScene, previous: QBrush) -> None:
    scene.set_export_mode(False)
    scene.setBackgroundBrush(previous)
    scene.update()


def export_png(
    scene: BoardScene,
    path: str | Path,
    scale: float = 2.0,
    background: str | QColor = "#ffffff",
) -> Path:
    target = Path(path)
    source, previous = _prepare_scene(scene, QColor(background))
    try:
        width = max(1, int(source.width() * scale))
        height = max(1, int(source.height() * scale))
        max_dimension = 12000
        if width > max_dimension or height > max_dimension:
            shrink = min(max_dimension / width, max_dimension / height)
            width = max(1, int(width * shrink))
            height = max(1, int(height * shrink))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(background))
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            scene.render(
                painter,
                QRectF(0.0, 0.0, float(width), float(height)),
                source,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        finally:
            painter.end()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target), "PNG"):
            raise ExportError(f"Could not write PNG file: {target}")
    except OSError as exc:
        raise ExportError(f"Could not write PNG file: {exc}") from exc
    finally:
        _finish_scene(scene, previous)
    if not target.exists() or target.stat().st_size == 0:
        raise ExportError("The exported PNG file is empty")
    return target


def export_pdf(
    scene: BoardScene,
    path: str | Path,
    background: str | QColor = "#ffffff",
) -> Path:
    target = Path(path)
    source, previous = _prepare_scene(scene, QColor(background))
    try:
        writer = QPdfWriter(str(target))
        writer.setResolution(300)
        writer.setTitle("Canvasity board")
        layout = writer.pageLayout()
        layout.setOrientation(
            QPageLayout.Orientation.Landscape
            if source.width() >= source.height()
            else QPageLayout.Orientation.Portrait
        )
        layout.setMargins(QMarginsF(18, 18, 18, 18))
        writer.setPageLayout(layout)

        painter = QPainter(writer)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            target_rect = QRectF(0.0, 0.0, float(writer.width()), float(writer.height()))
            scene.render(
                painter,
                target_rect,
                source,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        finally:
            painter.end()
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Could not write PDF file: {exc}") from exc
    finally:
        _finish_scene(scene, previous)
    if not target.exists() or target.stat().st_size == 0:
        raise ExportError("The exported PDF file is empty")
    return target
