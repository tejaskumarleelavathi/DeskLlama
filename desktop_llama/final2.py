#!/usr/bin/env python3
"""
desktop_llama/final.py
----------------------
Modern glass-morphism desktop assistant (Chat-only).
No mock fallbacks – requires working voice_module stack.
"""

import sys, asyncio, re
from enum import Enum

import httpx                              # still needed for AIWorker headers
from PyQt6.QtCore import Qt, QRectF, QTimer, QThread, pyqtSignal as Signal
from PyQt6.QtGui  import (QFont, QPainter, QPainterPath, QColor,
                           QPen, QLinearGradient, QBrush, QPixmap)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFrame, QGraphicsDropShadowEffect, QLineEdit,
    QScrollArea, QGridLayout
)
from PyQt6.QtSvgWidgets import QSvgWidget

from voice_module.llama_client   import next_step, LLAMA_KEY
from voice_module.screen_capture import capture_screen

# ────────────────────────────────────────────────────────────────── #
class AssistantMode(Enum):
    DISABLED = "Disabled"
    NORMAL   = "Normal"
    CHAT     = "Chat"

# ───── Glass-morphism helper widgets ────────────────────────────── #
class GlassmorphismButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(100, 40)
        self.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.set_active(False)

    def set_active(self, active: bool):
        style = (
            "background: rgba(0,122,255,0.8);"
            "border: 1px solid rgba(0,122,255,0.9);"
            "border-radius: 12px; color:white; font-weight:bold;"
        ) if active else (
            "background: rgba(255,255,255,0.1);"
            "border: 1px solid rgba(255,255,255,0.2);"
            "border-radius: 12px; color:white;"
        )
        self.setStyleSheet(f"QPushButton{{{style}}}"
                           "QPushButton:hover{background:rgba(255,255,255,0.15);}"
                           "QPushButton:pressed{background:rgba(255,255,255,0.08);}")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

class ChatMessage(QFrame):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.text, self.is_user = text, is_user
        self._build()

    def _build(self):
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 10, 12, 10)
        label = QLabel(self.text, wordWrap=True)
        label.setFont(QFont("Arial", 11))
        label.setStyleSheet("color:white; background:transparent;")
        label.setAlignment(Qt.AlignRight if self.is_user else Qt.AlignLeft)
        if self.is_user:
            lay.addStretch(); lay.addWidget(label)
        else:
            lay.addWidget(label); lay.addStretch()

    # bubble paint
    def paintEvent(self, _ev):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect(); path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 15, 15)
        if self.is_user:
            grad = QLinearGradient(0, 0, 0, rect.height())
            grad.setColorAt(0, QColor(0,122,255,180))
            grad.setColorAt(1, QColor(0,100,255,120))
            p.fillPath(path, QBrush(grad))
        else:
            p.fillPath(path, QBrush(QColor(255,255,255,30)))
        p.setPen(QPen(QColor(255,255,255,50), 1))
        p.drawPath(path)

# ───── Worker thread for async call ─────────────────────────────── #
class AIWorker(QThread):
    response_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, goal, img, prev, last):
        super().__init__()
        self.goal, self.img, self.prev, self.last = goal, img, prev, last

    def run(self):
        try:
            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            reply = loop.run_until_complete(self.fetch())
            self.response_ready.emit(reply)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            loop.close()

    async def fetch(self) -> str:
        headers = {"Authorization": f"Bearer {LLAMA_KEY}",
                   "Content-Type":  "application/json"}
        async with httpx.AsyncClient(timeout=60, headers=headers) as _:
            return await next_step(self.goal, self.img, self.prev, self.last)

# ───── Chat panel widget ────────────────────────────────────────── #
class ChatPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.prev, self.last = "", ""
        self.worker: AIWorker | None = None
        self._build()
        self._add_msg("Hi! I'm DeskLlama. How can I help you?", False)

    # UI
    def _build(self):
        self.setFixedSize(400, 350)
        main = QVBoxLayout(self); main.setContentsMargins(15,15,15,15)

        title = QLabel("Desk Llama Chat")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet("color:white;")
        main.addWidget(title, alignment=Qt.AlignCenter)

        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setStyleSheet("background:transparent; border:none;")
        self.chat_w = QWidget(); self.lay = QVBoxLayout(self.chat_w)
        self.lay.setSpacing(10); self.lay.addStretch()
        self.scroll.setWidget(self.chat_w)
        main.addWidget(self.scroll)

        # input row
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="Type a message…")
        self.input.setFont(QFont("Arial", 11))
        self.input.setStyleSheet(
            "QLineEdit{background:rgba(0,0,0,0.2); border:1px solid rgba(255,255,255,0.2);"
            "border-radius:18px; padding:10px; color:white}"
            "QLineEdit:focus{border-color:rgba(0,122,255,0.8)}")
        self.input.returnPressed.connect(self._send)
        btn = QPushButton("Send", clicked=self._send)
        btn.setFixedSize(70,36)
        btn.setStyleSheet(
            "QPushButton{background:#007AFF; border-radius:18px; color:white; font-weight:bold}"
            "QPushButton:hover{background:#006EE5}")
        row.addWidget(self.input); row.addWidget(btn)
        main.addLayout(row)

    # helpers
    def _add_msg(self, text: str, user: bool):
        self.lay.insertWidget(self.lay.count()-1, ChatMessage(text, user))
        QTimer.singleShot(10, lambda:
            self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()))

    # events
    def _send(self):
        text = self.input.text().strip()
        if not text: return
        self.input.clear()
        if text.lower() in {"exit","quit","bye","goodbye","stop"}:
            self._add_msg("Goodbye! Feel free to chat again anytime.", False)
            return

        self._add_msg(text, True)
        img = capture_screen()
        self._add_msg("Thinking…", False)                     # placeholder
        self.worker = AIWorker(text, img, self.prev, self.last)
        self.worker.response_ready.connect(self._reply)
        self.worker.error_occurred.connect(self._error)
        self.worker.finished.connect(lambda: self.worker.deleteLater())
        self.worker.start()

    def _reply(self, msg: str):
        self._remove_thinking(); self._add_msg(msg, False)
        self.prev += f" USER:{msg}"; self.last = msg

    def _error(self, err: str):
        self._remove_thinking(); self._add_msg(f"Error: {err}", False)

    def _remove_thinking(self):
        if self.lay.count() > 1:
            w = self.lay.itemAt(self.lay.count()-2).widget()
            if isinstance(w, ChatMessage) and w.text == "Thinking…":
                w.deleteLater()

# ───── Control panel (Disabled / Normal / Chat) ─────────────────── #
class ControlPanel(QFrame):
    mode_changed = Signal(AssistantMode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(400,120)
        lay = QVBoxLayout(self); lay.setContentsMargins(25,20,25,20)

        # title
        tbox = QHBoxLayout(alignment=Qt.AlignCenter)
        icon = QLabel(); icon.setPixmap(QPixmap("assets/meta.png").scaled(24,24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel("Desk Llama", font=QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:white;")
        tbox.addWidget(icon); tbox.addWidget(title); lay.addLayout(tbox)

        # buttons
        row = QHBoxLayout()
        self.btns = {
            AssistantMode.DISABLED: GlassmorphismButton("Disabled"),
            AssistantMode.NORMAL:   GlassmorphismButton("Normal"),
            AssistantMode.CHAT:     GlassmorphismButton("Chat")
        }
        for m, b in self.btns.items():
            b.clicked.connect(lambda _=None, mode=m: self.set_mode(mode))
            row.addWidget(b)
        lay.addLayout(row)
        self.set_mode(AssistantMode.DISABLED)

    def set_mode(self, mode: AssistantMode):
        for m,b in self.btns.items(): b.set_active(m==mode)
        self.mode_changed.emit(mode)

# ───── Main floating window ─────────────────────────────────────── #
class SimpleAssistant(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags( Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.layout = QGridLayout(self); self.layout.setContentsMargins(0,10,15,10)

        self.panel = ControlPanel(self); self.panel.mode_changed.connect(self._mode)
        self.layout.addWidget(self.panel, 0,0,1,2)

        self.status = QLabel("Desk Llama: Disabled", font=QFont("Arial",11))
        self.status.setStyleSheet("color:white; margin-top:5px;")
        self.status.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status, 1,0,1,2)

        self.chat: ChatPanel | None = None
        self._mode(AssistantMode.DISABLED)
        self._drag_pos = None
        self._raise_timer()

    # keep window on top
    def _raise_timer(self):
        timer = QTimer(self); timer.timeout.connect(lambda: (self.raise_(), self.activateWindow()))
        timer.start(100)

    # mode switch
    def _mode(self, mode: AssistantMode):
        if mode is AssistantMode.CHAT:
            if not self.chat:
                self.chat = ChatPanel(self)
                self.layout.addWidget(self.chat, 1,0,1,2)
            self.chat.show(); self.status.hide()
        else:
            if self.chat: self.chat.hide()
            self.status.setText(f"Desk Llama: {mode.value}")
            self.status.show()
        self._resize(mode)

    def _resize(self, mode):
        w,h = (400,500) if mode is AssistantMode.CHAT else (400,180)
        scr  = QApplication.primaryScreen().geometry()
        self.setFixedSize(w,h)
        self.move(scr.width()-w-30, 30)

    # paint rounded translucent window
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()), 20, 20)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0,QColor(50,50,50,220)); grad.setColorAt(1,QColor(30,30,30,220))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255,255,255,80),1)); p.drawPath(path)

    # drag
    def mousePressEvent(self, e):  self._drag_pos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self._drag_pos:
            self.move(self.pos()+e.globalPosition().toPoint()-self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

# ───── entry-point ──────────────────────────────────────────────── #
def main():
    app = QApplication(sys.argv)
    SimpleAssistant().show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
