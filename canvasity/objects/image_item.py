"""Bitmap images embedded in the board."""

from __future__ import annotations

import base64
from typing import Any

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from .base import BoardItem


def encode_pixmap(pixmap: QPixmap) -> str:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise ValueError("Could not encode image as PNG")
    data = bytes(buffer.data())
    buffer.close()
    return base64.b64encode(data).decode("ascii")


def decode_image(data: str) -> QImage:
    try:
        raw = base64.b64decode(data.encode("ascii"), validate=False)
    except Exception as exc:  # noqa: BLE001 - surface a clear storage error
        raise ValueError("Image data is not valid base64") from exc
    image = QImage.fromData(QByteArray(raw))
    if image.isNull():
        raise ValueError("Embedded image data could not be decoded")
    return image


class ImageItem(BoardItem):
    TYPE = "image"

    def __init__(self, pixmap: QPixmap, width: float = 0.0, height: float = 0.0) -> None:
        super().__init__()
        if pixmap.isNull():
            raise ValueError("Image is empty or could not be loaded")
        self._pixmap = QPixmap(pixmap)
        if width <= 0.0 or height <= 0.0:
            width = float(max(1, pixmap.width()))
            height = float(max(1, pixmap.height()))
        self.set_size(width, height)

    @classmethod
    def from_file(cls, path: str, max_dimension: float = 640.0) -> "ImageItem":
        pixmap = QPixmap(path)
        if pixmap.isNull():
            raise ValueError(f"Could not load image: {path}")
        width = float(pixmap.width())
        height = float(pixmap.height())
        if width > max_dimension or height > max_dimension:
            scale = min(max_dimension / width, max_dimension / height)
            width *= scale
            height *= scale
        return cls(pixmap, width, height)

    @classmethod
    def from_base64(cls, data: str, width: float, height: float) -> "ImageItem":
        image = decode_image(data)
        return cls(QPixmap.fromImage(image), width, height)

    @property
    def pixmap(self) -> QPixmap:
        return self._pixmap

    def set_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        self._pixmap = QPixmap(pixmap)
        self.update()

    def paint_content(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        target = QRectF(0.0, 0.0, self._w, self._h)
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        painter.setPen(Qt.PenStyle.NoPen)

    def content_rect(self) -> QRectF:
        return self.mapToScene(self.rect()).boundingRect()

    def _extra_dict(self) -> dict[str, Any]:
        return {"data": encode_pixmap(self._pixmap), "format": "png"}
