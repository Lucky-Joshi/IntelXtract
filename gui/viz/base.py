"""Phase 18 shared canvas: off-screen renderable widgets + PNG/SVG export.

``VizWidget`` subclasses implement :meth:`draw`, which is used for both the
on-screen ``paintEvent`` and the exported PNG (``QImage``) / SVG
(``QSvgGenerator``) that reports embed (S18.5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import QBuffer, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QWidget

TITLE_FONT_SIZE = 13
SUB_FONT_SIZE = 9


def draw_empty(painter: QPainter, rect: QRectF, message: str) -> None:
    """Draw a muted 'no data' placeholder."""
    painter.setPen(QColor("#9aa0a6"))
    font = painter.font()
    font.setPointSize(SUB_FONT_SIZE)
    painter.setFont(font)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), message)


class VizWidget(QWidget):
    """QWidget whose content is produced by a single pure ``draw`` call."""

    background: ClassVar[str] = "#ffffff"
    margin: ClassVar[float] = 14.0

    def draw(self, painter: QPainter, rect: QRectF) -> None:
        """Paint the scene within ``rect``. Subclasses implement this."""
        raise NotImplementedError

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, QRectF(self.rect()))
        painter.end()

    def _paint(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(self.background))
        painter.setClipRect(rect)
        self.draw(painter, rect)

    def render_png(self, size: tuple[int, int] | None = None) -> bytes:
        """Render the widget to in-memory PNG bytes."""
        width, height = size or (self.width() or 800, self.height() or 600)
        image = QImage(int(width), int(height), QImage.Format.Format_ARGB32)
        image.fill(QColor(self.background))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, QRectF(0.0, 0.0, float(width), float(height)))
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")  # type: ignore[call-overload]
        return bytes(buffer.data())  # type: ignore[call-overload,no-any-return]

    def render_svg(self, size: tuple[int, int] | None = None) -> bytes:
        """Render the widget to in-memory SVG bytes."""
        width, height = size or (self.width() or 800, self.height() or 600)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        generator = QSvgGenerator()
        generator.setSize(QSize(int(width), int(height)))
        generator.setOutputDevice(buffer)
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, QRectF(0.0, 0.0, float(width), float(height)))
        painter.end()
        return bytes(buffer.data())  # type: ignore[call-overload,no-any-return]


def export_png(widget: VizWidget, path: str | None = None) -> bytes:
    """Render ``widget`` to PNG bytes, optionally writing them to ``path``."""
    data = widget.render_png()
    if path:
        Path(path).write_bytes(data)
    return data


def export_svg(widget: VizWidget, path: str | None = None) -> bytes:
    """Render ``widget`` to SVG bytes, optionally writing them to ``path``."""
    data = widget.render_svg()
    if path:
        Path(path).write_bytes(data)
    return data


def _title_text(painter: QPainter, rect: QRectF, text: str) -> QRectF:
    """Print a bold title and return the remaining body rect."""
    font = painter.font()
    font.setPointSize(TITLE_FONT_SIZE)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#202124"))
    painter.drawText(
        rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
        text,
    )
    body = QRectF(
        rect.x(),
        rect.y() + TITLE_FONT_SIZE + 10.0,
        rect.width(),
        rect.height() - (TITLE_FONT_SIZE + 10.0),
    )
    font.setBold(False)
    font.setPointSize(9)
    painter.setFont(font)
    return body


def _grid_pen() -> QPen:
    pen = QPen(QColor("#d0d5dc"))
    pen.setWidth(1)
    return pen


__all__ = [
    "VizWidget",
    "_grid_pen",
    "_title_text",
    "draw_empty",
    "export_png",
    "export_svg",
]
