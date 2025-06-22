"""
Qt-friendly wrapper that exposes async methods as Qt signals/slots.
"""
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal
from qasync import asyncSlot

from desktop_llama.backend import DeskLlamaCore


class BackendWorker(QObject):
    reply_ready = pyqtSignal(str)        # emitted when Llama has answered

    def __init__(self, parent=None):
        super().__init__(parent)
        self.core = DeskLlamaCore()

    # expose an awaitable slot to Qt ------------------------------------------
    @asyncSlot(str)
    async def ask(self, prompt: str):
        answer = await self.core.ask(prompt)
        self.reply_ready.emit(answer)
