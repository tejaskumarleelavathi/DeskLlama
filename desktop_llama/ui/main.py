#!/usr/bin/env python3
"""
Modern Glassmorphism AI Assistant (Desk Llama)
UI wired to real backend + voice toggle.
"""


import sys, asyncio
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QLineEdit, QScrollArea, QGridLayout
)
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QFont, QPainter, QPainterPath, QColor, QPen, QLinearGradient, QBrush, QPixmap
)
from enum import Enum
ASSETS = Path(__file__).resolve().parent.parent / "assets"
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import Qt
from qasync import QEventLoop
from desktop_llama.ui_worker import BackendWorker            # <── new import

# ───────── enums / tiny helpers ───────────────────────────────────────────────
class AssistantMode(Enum):
    DISABLED = "Disabled"
    NORMAL   = "Normal"
    CHAT     = "Chat"


# ───────── reusable widgets (unchanged styling) ──────────────────────────────
class GlassmorphismButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.is_active = False
        self.setup_style()

    def setup_style(self):
        self.setFixedSize(100, 40)
        self.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.set_active(False)

    def set_active(self, active: bool):
        self.is_active = active
        if active:
            self.setStyleSheet("""
                QPushButton { background: rgba(0,122,255,0.8);
                              border: 1px solid rgba(0,122,255,0.9);
                              border-radius: 12px; color: white; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: rgba(255,255,255,0.1);
                              border: 1px solid rgba(255,255,255,0.2);
                              border-radius: 12px; color: white; }
                QPushButton:hover  { background: rgba(255,255,255,0.15); }
                QPushButton:pressed{ background: rgba(255,255,255,0.08); }
            """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)


class ChatMessage(QFrame):
    def __init__(self, text: str, is_user=True, parent=None):
        super().__init__(parent)
        self.text     = text
        self.is_user  = is_user
        self.setup_ui()


    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        lbl = QLabel(self.text)
        lbl.setWordWrap(True)
        lbl.setFont(QFont("Arial", 11))
        lbl.setStyleSheet("color: white; background: transparent;")

        if self.is_user:
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addStretch()
            layout.addWidget(lbl)
        else:
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(lbl)
            layout.addStretch()

    def paintEvent(self, _evt):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 15, 15)

        if self.is_user:
            grad = QLinearGradient(0, 0, 0, rect.height())
            grad.setColorAt(0, QColor(0, 122, 255, 180))
            grad.setColorAt(1, QColor(0, 100, 255, 120))
            painter.fillPath(path, QBrush(grad))
        else:
            painter.fillPath(path, QBrush(QColor(255, 255, 255, 30)))

        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        painter.drawPath(path)


# ───────── control panel (mode buttons) ───────────────────────────────────────
class ControlPanel(QFrame):
    mode_changed = pyqtSignal(AssistantMode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.setFixedSize(400, 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        # title
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.setSpacing(10)

        icon = QLabel()
        meta_path = ASSETS / "meta.png"
        icon.setPixmap(QPixmap(str(meta_path)).scaled(
            24, 24,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

        title = QLabel("Desk Llama")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        title_row.addWidget(icon)
        title_row.addWidget(title)
        layout.addLayout(title_row)

        # buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        self.btn_disabled = GlassmorphismButton("Disabled")
        self.btn_normal   = GlassmorphismButton("Normal")
        self.btn_chat     = GlassmorphismButton("Chat")

        self.btn_disabled.clicked.connect(
            lambda: self.set_mode(AssistantMode.DISABLED)
        )
        self.btn_normal.clicked.connect(
            lambda: self.set_mode(AssistantMode.NORMAL)
        )
        self.btn_chat.clicked.connect(
            lambda: self.set_mode(AssistantMode.CHAT)
        )

        btn_row.addWidget(self.btn_disabled)
        btn_row.addWidget(self.btn_normal)
        btn_row.addWidget(self.btn_chat)
        layout.addLayout(btn_row)

        self.btn_disabled.set_active(True)

    # -------------------------------------------------------------------------
    def set_mode(self, mode: AssistantMode):
        self.btn_disabled.set_active(mode == AssistantMode.DISABLED)
        self.btn_normal.set_active(mode == AssistantMode.NORMAL)
        self.btn_chat.set_active(mode == AssistantMode.CHAT)
        self.mode_changed.emit(mode)


# ───────── chat panel wired to backend worker ────────────────────────────────
class ChatPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.add_welcome()
        # backend
        self.worker = BackendWorker(self)
        self.worker.reply_ready.connect(
            lambda txt: self.add_message(txt, is_user=False)
        )

    # -------------------------------------------------------------------------
    def setup_ui(self):
        self.setFixedSize(400, 350)
        main = QVBoxLayout(self)
        main.setContentsMargins(15, 15, 15, 15)
        main.setSpacing(10)

        # title
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.setSpacing(10)
        icon = QLabel()
        meta_path = ASSETS / "meta.png"
        icon.setPixmap(QPixmap(str(meta_path)).scaled(20, 20,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        label = QLabel("Desk Llama Chat")
        label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        label.setStyleSheet("color: white;")
        title_row.addWidget(icon)
        title_row.addWidget(label)
        main.addLayout(title_row)

        # scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_widget)
        main.addWidget(self.scroll)

        # input row
        input_row = QHBoxLayout()
        self.line = QLineEdit()
        self.line.setPlaceholderText("Type a message…")
        self.line.setFont(QFont("Arial", 11))
        self.line.setStyleSheet(
            "QLineEdit { background: rgba(0,0,0,0.2);"
            "border: 1px solid rgba(255,255,255,0.2); border-radius: 18px;"
            "padding: 10px; color: white; }"
            "QLineEdit:focus { border-color: rgba(0,122,255,0.8); }"
        )
        self.line.returnPressed.connect(self.send_message)

        send_btn = QPushButton("Send")
        send_btn.setFixedSize(70, 36)
        send_btn.setStyleSheet(
            "QPushButton { background-color:#007AFF; border-radius:18px;"
            "color:white; font-weight:bold; }"
            "QPushButton:hover { background-color:#006EE5; }"
        )
        send_btn.clicked.connect(self.send_message)
        input_row.addWidget(self.line)
        input_row.addWidget(send_btn)
        main.addLayout(input_row)

    # -------------------------------------------------------------------------
    def add_message(self, text: str, is_user=True):
        msg = ChatMessage(text, is_user)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, msg)
        QTimer.singleShot(
            10,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )

    def add_welcome(self):
        self.add_message("Hi! I’m Desk Llama.", is_user=False)

    # -------------------------------------------------------------------------
    def send_message(self):
        user_text = self.line.text().strip()
        if not user_text:
            return
        self.add_message(user_text, is_user=True)
        self.line.clear()
        # async call via qasync
        self.worker.ask(user_text)


# ───────── main window ───────────────────────────────────────────────────────
class SimpleAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.chat_panel: ChatPanel | None = None
        self.is_mic_on = False
        self.drag_pos  = None
        self._speech_task = None
        self._cancel_evt = asyncio.Event()

        self.setup_ui()
        self.setup_timer()
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.close)

    # -------------------------------------------------------------------------
    def setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 10, 15, 10)

        # control panel
        self.ctrl = ControlPanel(self)
        self.ctrl.mode_changed.connect(self.on_mode_changed)
        self.layout.addWidget(self.ctrl, 0, 0, 1, 2)

        # status label
        self.status = QLabel("Desk Llama: Disabled")
        self.status.setFont(QFont("Arial", 11))
        self.status.setStyleSheet("color:white; margin-top:5px;")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.status, 1, 0, 1, 2)
        self.layout.setRowStretch(2, 1)

        # mic icon
        self.mic = QSvgWidget()
        self.mic.setFixedSize(20, 20)
        self.mic.setToolTip("Click to toggle microphone")
        self.mic.mousePressEvent = self.toggle_mic
        self.layout.addWidget(self.mic, 3, 1, Qt.AlignmentFlag.AlignRight)

        self.on_mode_changed(AssistantMode.DISABLED)
        self.setWindowTitle("Desk Llama")
        self.update_mic_icon()

    def setup_timer(self):
        t = QTimer(self)
        t.timeout.connect(self.ensure_on_top)
        t.start(100)

    # -------------------------------------------------------------------------
    def ensure_on_top(self):
        if not self.isActiveWindow():
            self.raise_()
            self.activateWindow()

    # mode switching -----------------------------------------------------------
    def on_mode_changed(self, mode: AssistantMode):
        if mode == AssistantMode.CHAT:
            if self.chat_panel is None:
                self.chat_panel = ChatPanel(self)
                self.layout.addWidget(self.chat_panel, 1, 0, 1, 2)
            self.chat_panel.show()
            self.status.hide()
        else:
            if self.chat_panel:
                self.chat_panel.hide()
            self.status.setText(f"Desk Llama: {mode.value}")
            self.status.show()
        self.resize_for_mode(mode)

    def resize_for_mode(self, mode: AssistantMode):
        w, h = ((400, 500) if mode == AssistantMode.CHAT else (400, 180))
        screen = QApplication.primaryScreen().geometry()
        margin = 30
        self.setFixedSize(w, h)
        self.move(screen.width() - w - margin, margin)



    def toggle_mic(self, _evt):
        if self._speech_task and not self._speech_task.done():
            # ── stop current loop ───────────────────────────────
            self._cancel_evt.set()
            self._speech_task.cancel()
            self._speech_task = None
            self._cancel_evt  = asyncio.Event()
        else:
            # ── start a fresh speech loop ───────────────────────
            from desktop_llama.backend import DeskLlamaCore
            core = (
                self.chat_panel.worker.core
                if self.chat_panel else DeskLlamaCore()
            )
            self._speech_task = asyncio.create_task(
                core.speech_loop(self._cancel_evt)   # ← your method
            )
        self.is_mic_on = not self.is_mic_on
        self.update_mic_icon()

    def update_mic_icon(self):
        assets = Path(__file__).resolve().parent.parent / "assets"
        icon = assets / ("mic_on.svg" if self.is_mic_on else "mic_off.svg")
        self.mic.load(str(icon))
        self.mic.setToolTip("Microphone is On" if self.is_mic_on
                            else "Microphone is Off")

    # window niceties ----------------------------------------------------------
    def paintEvent(self, _evt):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 20, 20)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(50, 50, 50, 220))
        grad.setColorAt(1, QColor(30, 30, 30, 220))
        painter.fillPath(path, QBrush(grad))

        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        painter.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self.drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self.drag_pos)
            self.drag_pos = e.globalPosition().toPoint()





# ───────── bootstrap ─────────────────────────────────────────────────────────
def main():
    app  = QApplication(sys.argv)
    loop = QEventLoop(app)             # qasync magic
    asyncio.set_event_loop(loop)

    ui = SimpleAssistant()
    ui.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
