#!/usr/bin/env python3
"""
Modern Glassmorphism AI Assistant
A beautiful transparent control panel inspired by modern macOS design.
"""

import sys
import platform
import asyncio
import re
import httpx
from enum import Enum
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFrame, QGraphicsDropShadowEffect,
    QLineEdit, QScrollArea, QGridLayout
)
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QTimer, QThread, pyqtSignal as Signal
from PyQt6.QtGui import (
    QFont, QPainter, QPainterPath, QColor, QPen,
    QLinearGradient, QBrush, QPixmap
)

# Import text module functionality
try:
    from voice_module.llama_client import next_step, LLAMA_KEY, ENDPOINT, MODEL
    from voice_module.screen_capture import capture_screen
    print("✅ Using text module functionality")
except ImportError as e:
    try:
        # Try direct import if relative import fails
        from voice_module.llama_client import next_step, LLAMA_KEY, ENDPOINT, MODEL
        from voice_module.screen_capture import capture_screen
        print("✅ Using text module functionality")
    except ImportError as e2:
        print(f"⚠️  text module not found: {e2}")
        print("Using mock functions...")
        

        
        # Mock functions for testing
        async def next_step(client, goal, img, prev, last, *,stream: bool = False,):
            await asyncio.sleep(0.5)
            if "hello" in goal.lower() or "hi" in goal.lower():
                return "Hello! I'm DeskLlama. How can I help you today?"
            elif "screen" in goal.lower():
                return f"I can see your screen (captured {img.size if img else 'no image'}). What would you like me to help with?"
            elif "help" in goal.lower():
                return "I'm here to help! I can see your screen and assist with various tasks. What do you need?"
            else:
                return f"I understand you're asking about: '{goal}'. This is a mock response - replace with your actual AI model!"
        
        def capture_screen():
            from PIL import Image
            return Image.new('RGB', (100, 100), color='black')
        
        LLAMA_KEY, ENDPOINT, MODEL = None, None, None

class AssistantMode(Enum):
    DISABLED = "Disabled"
    NORMAL = "Normal" 
    CHAT = "Chat"

class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class GlassmorphismButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.is_active = False
        self.setup_style()
        
    def setup_style(self):
        self.setFixedSize(100, 40)
        self.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.set_active(False)

    def set_active(self, active):
        self.is_active = active
        if active:
            self.setStyleSheet("""
                QPushButton { background: rgba(0, 122, 255, 0.8); border: 1px solid rgba(0, 122, 255, 0.9); border-radius: 12px; color: white; font-weight: bold; }
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; color: white; }
                QPushButton:hover { background: rgba(255, 255, 255, 0.15); }
                QPushButton:pressed { background: rgba(255, 255, 255, 0.08); }
            """)
        shadow = QGraphicsDropShadowEffect(self); shadow.setBlurRadius(20); shadow.setColor(QColor(0, 0, 0, 80)); shadow.setOffset(0, 2); self.setGraphicsEffect(shadow)

class ChatMessage(QFrame):
    def __init__(self, text, is_user=True, parent=None):
        super().__init__(parent)
        self.text = text
        self.is_user = is_user
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self); layout.setContentsMargins(12, 10, 12, 10)
        self.message_label = QLabel(self.text); self.message_label.setWordWrap(True); self.message_label.setFont(QFont("Arial", 11)); self.message_label.setStyleSheet("color: white; background: transparent;")
        if self.is_user: self.message_label.setAlignment(Qt.AlignmentFlag.AlignRight); layout.addStretch(); layout.addWidget(self.message_label)
        else: self.message_label.setAlignment(Qt.AlignmentFlag.AlignLeft); layout.addWidget(self.message_label); layout.addStretch()
        
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect(); path = QPainterPath(); path.addRoundedRect(QRectF(rect), 15, 15)
        if self.is_user:
            gradient = QLinearGradient(0, 0, 0, rect.height()); gradient.setColorAt(0, QColor(0, 122, 255, 180)); gradient.setColorAt(1, QColor(0, 100, 255, 120)); painter.fillPath(path, QBrush(gradient))
        else: painter.fillPath(path, QBrush(QColor(255, 255, 255, 30)))
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1)); painter.drawPath(path)

class AIWorker(QThread):
    response_ready = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, goal, img, prev, last, task_mode):
        super().__init__()
        self.goal = goal
        self.img = img
        self.prev = prev
        self.last = last
        self.task_mode = task_mode
    
    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(self.get_ai_response())
            self.response_ready.emit(response)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            loop.close()

    async def get_ai_response(self):
        headers = {
            "Authorization": f"Bearer {LLAMA_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60, headers=headers) as client:
            return await next_step(
                client, self.goal, self.img, self.prev, self.last, self.task_mode
            )

class ControlPanel(QFrame):
    mode_changed = pyqtSignal(AssistantMode)
    def __init__(self, parent=None):
        super().__init__(parent); self.setup_ui()
    def setup_ui(self):
        self.setFixedSize(400, 120); layout = QVBoxLayout(self); layout.setContentsMargins(25, 20, 25, 20); layout.setSpacing(15)
        title_layout = QHBoxLayout(); title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter); title_layout.setSpacing(10)
        icon_label = QLabel(); pixmap = QPixmap("/Users/suriya/Documents/Github/NaviLLaMA/assets/meta.png"); icon_label.setPixmap(pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title_text = QLabel("Desk Llama"); title_text.setFont(QFont("Arial", 16, QFont.Weight.Bold)); title_text.setStyleSheet("color: white;")
        title_layout.addWidget(icon_label); title_layout.addWidget(title_text); layout.addLayout(title_layout)
        button_container = QHBoxLayout(); button_container.setSpacing(15)
        self.disabled_btn = GlassmorphismButton("Disabled"); self.normal_btn = GlassmorphismButton("Normal"); self.chat_btn = GlassmorphismButton("Chat")
        self.disabled_btn.clicked.connect(lambda: self.set_mode(AssistantMode.DISABLED)); self.normal_btn.clicked.connect(lambda: self.set_mode(AssistantMode.NORMAL)); self.chat_btn.clicked.connect(lambda: self.set_mode(AssistantMode.CHAT))
        button_container.addWidget(self.disabled_btn); button_container.addWidget(self.normal_btn); button_container.addWidget(self.chat_btn); layout.addLayout(button_container)
        self.disabled_btn.set_active(True)
    def set_mode(self, mode): self.disabled_btn.set_active(mode == AssistantMode.DISABLED); self.normal_btn.set_active(mode == AssistantMode.NORMAL); self.chat_btn.set_active(mode == AssistantMode.CHAT); self.mode_changed.emit(mode)

class ChatPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.prev = ""  # conversation history
        self.last = ""  # last AI response
        self.task_mode = False  # FALSE = Q/A, TRUE = numbered guide
        self.ai_worker = None  # Track the current AI worker
        self.setup_ui()
        self.add_welcome_message()
    
    def setup_ui(self):
        self.setFixedSize(400, 350)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.setSpacing(10)
        
        icon_label = QLabel()
        pixmap = QPixmap("/Users/suriya/Documents/Github/NaviLLaMA/assets/meta.png")
        icon_label.setPixmap(pixmap.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        title_text = QLabel("Desk Llama Chat")
        title_text.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_text.setStyleSheet("color: white;")
        
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_text)
        main_layout.addLayout(title_layout)
        
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("background: transparent; border: none;")
        
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_widget)
        main_layout.addWidget(self.chat_scroll)
        
        input_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.setFont(QFont("Arial", 11))
        self.message_input.setStyleSheet("""
            QLineEdit { 
                background: rgba(0, 0, 0, 0.2); 
                border: 1px solid rgba(255, 255, 255, 0.2); 
                border-radius: 18px; 
                padding: 10px; 
                color: white; 
            } 
            QLineEdit:focus { 
                border-color: rgba(0, 122, 255, 0.8); 
            }
        """)
        self.message_input.returnPressed.connect(self.send_message)
        
        self.send_button = QPushButton("Send")
        self.send_button.setFixedSize(70, 36)
        self.send_button.setStyleSheet("""
            QPushButton { 
                background-color: #007AFF; 
                border-radius: 18px; 
                color: white; 
                font-weight: bold; 
            } 
            QPushButton:hover { 
                background-color: #006EE5; 
            }
        """)
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        main_layout.addLayout(input_layout)
    
    def add_message(self, text, is_user=True):
        message = ChatMessage(text, is_user)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, message)
        QTimer.singleShot(10, lambda: self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum()))
    
    def add_welcome_message(self):
        self.add_message("Hi! I'm Desk Llama. I can see your screen and help you with tasks. What would you like to do?", is_user=False)
    
    def send_message(self):
        user_text = self.message_input.text().strip()
        if not user_text:
            return
        
        # Add user message to chat
        self.add_message(user_text, is_user=True)
        self.message_input.clear()
        
        # Check for exit commands
        break_words = {"exit", "quit", "bye", "goodbye", "stop"}
        if any(word in user_text.lower() for word in break_words):
            self.add_message("Goodbye! Feel free to chat again anytime.", is_user=False)
            return
        
        # Process the message with AI
        self.process_with_ai(user_text)
    
    def process_with_ai(self, user_text):
        # Clean up any existing AI worker
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.quit()
            self.ai_worker.wait()
        
        # Capture screen
        try:
            img = capture_screen()
        except Exception as e:
            print(f"Error capturing screen: {e}")
            img = None
        
        # Check for task mode triggers
        task_triggers = ("how do i", "click", "which", "where")
        if any(trigger in user_text.lower() for trigger in task_triggers):
            self.task_mode = True
        
        # Create and start AI worker
        self.ai_worker = AIWorker(user_text, img, self.prev, self.last, self.task_mode)
        self.ai_worker.response_ready.connect(self.handle_ai_response)
        self.ai_worker.error_occurred.connect(self.handle_ai_error)
        self.ai_worker.finished.connect(self.cleanup_ai_worker)
        self.ai_worker.start()
        
        # Show typing indicator
        self.add_message("Thinking...", is_user=False)
    
    def handle_ai_response(self, response):
        # Remove the "Thinking..." message
        if self.chat_layout.count() > 1:
            thinking_widget = self.chat_layout.itemAt(self.chat_layout.count() - 2).widget()
            if isinstance(thinking_widget, ChatMessage) and thinking_widget.text == "Thinking...":
                thinking_widget.deleteLater()
        
        # Add AI response
        self.add_message(response, is_user=False)
        
        # Update conversation history
        self.last = response
        self.prev += f" USER: {response}"
        
        # Check for task completion
        if re.search(r"(goal|task) complete|anything else", response, re.I):
            self.task_mode = False
        
        # Check for polite acknowledgements
        polite_words = ("thanks", "thank you", "ok", "okay", "got it", "done")
        if any(word in response.lower() for word in polite_words):
            self.task_mode = False
    
    def handle_ai_error(self, error):
        # Remove the "Thinking..." message
        if self.chat_layout.count() > 1:
            thinking_widget = self.chat_layout.itemAt(self.chat_layout.count() - 2).widget()
            if isinstance(thinking_widget, ChatMessage) and thinking_widget.text == "Thinking...":
                thinking_widget.deleteLater()
        
        # Add error message
        self.add_message(f"Sorry, I encountered an error: {error}", is_user=False)
    
    def cleanup_ai_worker(self):
        """Clean up the AI worker thread"""
        if self.ai_worker:
            self.ai_worker.deleteLater()
            self.ai_worker = None

class SimpleAssistant(QWidget):
    def __init__(self):
        super().__init__(); self.chat_panel = None; self.is_mic_on = False; self.drag_pos = None; self.setup_ui(); self.setup_timer()
    def setup_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.main_layout = QGridLayout(self); self.main_layout.setContentsMargins(0, 10, 15, 10)
        self.control_panel = ControlPanel(self); self.control_panel.mode_changed.connect(self.on_mode_changed); self.main_layout.addWidget(self.control_panel, 0, 0, 1, 2)
        self.status_label = QLabel("Desk Llama: Disabled"); self.status_label.setFont(QFont("Arial", 11)); self.status_label.setStyleSheet("color: white; margin-top: 5px;"); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.main_layout.addWidget(self.status_label, 1, 0, 1, 2)
        self.main_layout.setRowStretch(2, 1)
        self.mic_widget = QSvgWidget(); self.mic_widget.setFixedSize(20, 20); self.mic_widget.setToolTip("Click to toggle microphone"); self.mic_widget.mousePressEvent = self.toggle_mic; self.main_layout.addWidget(self.mic_widget, 3, 1, Qt.AlignmentFlag.AlignRight)
        self.on_mode_changed(AssistantMode.DISABLED); self.setWindowTitle("Desk Llama"); self.update_mic_status()
    def setup_timer(self):
        self.timer = QTimer(self); self.timer.timeout.connect(self.ensure_on_top); self.timer.start(100)
    def ensure_on_top(self):
        if self.isActiveWindow(): return
        self.raise_(); self.activateWindow()
    def on_mode_changed(self, mode):
        if mode == AssistantMode.CHAT:
            if self.chat_panel is None: self.chat_panel = ChatPanel(self); self.main_layout.addWidget(self.chat_panel, 1, 0, 1, 2)
            self.chat_panel.show()
            self.status_label.hide()
            self.mic_widget.hide()
        else:
            if self.chat_panel: self.chat_panel.hide()
            self.status_label.setText(f"Desk Llama: {mode.value}")
            self.status_label.show()
            self.mic_widget.show()
        self.resize_for_mode(mode)
    def resize_for_mode(self, mode):
        width, height = (400, 500) if mode == AssistantMode.CHAT else (400, 180)
        screen = QApplication.primaryScreen().geometry(); margin = 30
        new_x = screen.width() - width - margin; new_y = margin
        self.setFixedSize(width, height); self.move(new_x, new_y)
    def toggle_mic(self, event):
        self.is_mic_on = not self.is_mic_on; self.update_mic_status()
        print(f"🎤 Mic status toggled: {'On' if self.is_mic_on else 'Off'}")
    def update_mic_status(self):
        path = "assets/mic_on.svg" if self.is_mic_on else "assets/mic_off.svg"
        # path = "assets"
        self.mic_widget.load(path)
        self.mic_widget.setToolTip("Microphone is On" if self.is_mic_on else "Microphone is Off")
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(self.rect()), 20, 20)
        gradient = QLinearGradient(0, 0, 0, self.height()); gradient.setColorAt(0, QColor(50, 50, 50, 220)); gradient.setColorAt(1, QColor(30, 30, 30, 220))
        painter.fillPath(path, QBrush(gradient)); painter.setPen(QPen(QColor(255, 255, 255, 80), 1)); painter.drawPath(path)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.drag_pos = event.globalPosition().toPoint()
    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() == Qt.MouseButton.LeftButton: self.move(self.pos() + event.globalPosition().toPoint() - self.drag_pos); self.drag_pos = event.globalPosition().toPoint()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()

def main():
    app = QApplication(sys.argv); assistant = SimpleAssistant(); assistant.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()