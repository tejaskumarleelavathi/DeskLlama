# voice_number_clicker.py
"""
Speak‑a‑Number ➜ Click‑a‑Button
================================
A *minimal* bridge that does exactly one thing:
    • Listens to your microphone with **RivaAudioAgent** (or Whisper etc.).
    • Extracts the first number it hears (spoken digits *or* words “one … ten”).
    • Finds that badge number in the running **windows_overlay** instance and
      clicks it.

There’s **no fallback to Llama**, no screen capture, no TTS chatter unless
something goes wrong – perfect for hands‑free UI poking.

Run order
---------
1. Start the numbered overlay in one terminal:

   ```powershell
   python desktop_llama/ui/windows_overlay.py
   ```

2. In another terminal (same Conda env):

   ```powershell
   python voice_module/voice_number_clicker.py
   ```

Say “press four”, “click twelve”, “select nine”… the corresponding control
gets invoked.
"""
from __future__ import annotations

import asyncio, re
from typing import Optional

from PyQt6.QtCore import QCoreApplication

import uiautomation as auto

# ── voice pipeline (your existing code) ───────────────────────────────────────
from voice_module.riva_agent import RivaAudioAgent   # ASR
from voice_module.voice_agent import speak           # optional feedback

# ── overlay import (already running in another process) ───────────────────────
try:
    from ui.windows_overlay import Overlay           # ← adjust if path differs
except ImportError:
    raise RuntimeError("windows_overlay must be importable – check PYTHONPATH.")

# ── number capture helpers ────────────────────────────────────────────────────
WORD2NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
DIGIT_RE = re.compile(r"\b(\d{1,3})\b")  # up to 3‑digit numbers
WORD_RE  = re.compile(r"\b(" + "|".join(WORD2NUM.keys()) + r")\b", re.I)


def extract_number(text: str) -> Optional[int]:
    """Return the first integer mentioned in *text* (digits or words)."""
    m = DIGIT_RE.search(text)
    if m:
        return int(m.group(1))
    m = WORD_RE.search(text)
    if m:
        return WORD2NUM[m.group(1).lower()]
    return None

# ── overlay helper ────────────────────────────────────────────────────────────

def get_overlay_instance() -> Optional[Overlay]:
    app = QCoreApplication.instance()
    if not app:
        return None
    for w in app.allWidgets():
        if isinstance(w, Overlay):
            return w
    return None


async def click_badge(num: int) -> bool:
    """Try to click *num* in the running overlay."""
    ov = get_overlay_instance()
    if not ov:
        return False
    elem = next((e for e in ov.elements if e.number == num), None)
    if not elem:
        return False
    ov._invoke(elem)
    return True

# ── main async loop ───────────────────────────────────────────────────────────
async def main():
    listener = RivaAudioAgent()
    speak("Number‑to‑click listener ready.")

    while True:
        utterance = (await listener.listen()).strip()
        if not utterance:
            continue
        print("[User]", utterance)
        num = extract_number(utterance)
        if num is None:
            speak("Sorry, I didn't catch a number.")
            continue
        if await click_badge(num):
            speak(f"Clicked {num}.")
        else:
            speak(f"Badge {num} not found.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        speak("Voice clicker stopped.")
