"""Reusable UI widgets shared across tabs."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ada_research.ui.theme import COLORS


class Card(QFrame):
    """Bordered panel used as a container for grouped content.

    Apply consistent card styling without each tab redoing the QSS.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)


class StatCard(QFrame):
    """A KPI-style card: large value on top, label below.

    Used heavily on the macro dashboard and the sentiment overview.
    """

    def __init__(
        self,
        label: str,
        value: str = "—",
        sublabel: str | None = None,
        tone: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._label_widget = QLabel(label)
        self._label_widget.setObjectName("dim")

        self._value_widget = QLabel(value)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._value_widget.setFont(font)

        self._sublabel_widget = QLabel(sublabel or "")
        self._sublabel_widget.setObjectName("dim")
        self._sublabel_widget.setVisible(bool(sublabel))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(self._label_widget)
        layout.addWidget(self._value_widget)
        layout.addWidget(self._sublabel_widget)

        self.set_tone(tone)

    def set_value(self, value: str, sublabel: str | None = None) -> None:
        self._value_widget.setText(value)
        if sublabel is not None:
            self._sublabel_widget.setText(sublabel)
            self._sublabel_widget.setVisible(bool(sublabel))

    def set_tone(self, tone: str) -> None:
        """Tone: 'good' | 'bad' | 'warn' | 'neutral'."""
        color_map = {
            "good": COLORS["good"],
            "bad": COLORS["bad"],
            "warn": COLORS["warn"],
            "neutral": COLORS["text"],
        }
        color = color_map.get(tone, COLORS["text"])
        self._value_widget.setStyleSheet(f"color: {color};")


class SignalBadge(QLabel):
    """Colored pill showing BUY / HOLD / SELL etc."""

    SIGNAL_COLORS = {
        "STRONG_BUY":  (COLORS["good"], "white"),
        "BUY":         (COLORS["good_dim"], COLORS["good"]),
        "HOLD":        (COLORS["warn_dim"], COLORS["warn"]),
        "SELL":        (COLORS["bad_dim"], COLORS["bad"]),
        "STRONG_SELL": (COLORS["bad"], "white"),
    }

    def __init__(self, signal: str = "HOLD", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(110)
        self.setMaximumHeight(28)
        self.set_signal(signal)

    def set_signal(self, signal: str) -> None:
        signal = signal.upper().replace(" ", "_")
        bg, fg = self.SIGNAL_COLORS.get(signal, (COLORS["panel"], COLORS["text"]))
        self.setText(signal.replace("_", " "))
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; "
            f"border-radius: 4px; padding: 4px 10px; font-weight: 600;"
        )


class PlaceholderPanel(QWidget):
    """Shown when a tab can't operate because a config value is missing.

    Most tabs need an API key. Rather than crashing or showing a broken UI,
    we render this panel with a clear message and a 'Reload' button.
    """

    reload_requested = pyqtSignal()

    def __init__(
        self,
        title: str,
        message: str,
        action_label: str = "Reload",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        title_label = QLabel(title)
        title_label.setObjectName("h2")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        message_label = QLabel(message)
        message_label.setObjectName("dim")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setMaximumWidth(520)

        button = QPushButton(action_label)
        button.setObjectName("primary")
        button.clicked.connect(self.reload_requested.emit)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)
        layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(16)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)


class HSeparator(QFrame):
    """Horizontal divider line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"color: {COLORS['border']};")


class ToolbarRow(QWidget):
    """A horizontal row used as an inline toolbar inside a tab."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        self._layout.setSpacing(8)

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_stretch(self) -> None:
        self._layout.addStretch(1)
