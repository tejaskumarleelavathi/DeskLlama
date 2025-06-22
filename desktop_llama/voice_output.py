"""
Blocking SAPI-5 text-to-speech for Windows.
• No edge-tts or ffmpeg → zero crashes.
• Speak() prints to console and waits until audio finishes.
"""
import atexit, pyttsx3, comtypes, threading, sys

# ── init engine ──────────────────────────────────────────────────────
_tts = pyttsx3.init("sapi5")
for v in _tts.getProperty("voices"):
    if any(k in v.name.lower() for k in ("aria", "zira", "jenny", "guy", "david")):
        _tts.setProperty("voice", v.id); break
_tts.setProperty("rate", 185)

_lock = threading.Lock()

def speak(text: str) -> None:
    """Print and speak synchronously (thread-safe)."""
    print(f"Assistant: {text}")
    with _lock:
        try:
            _tts.say(text)
            _tts.runAndWait()
        except Exception as e:
            print("[TTS error]", e, file=sys.stderr)

atexit.register(lambda: _tts.stop())

# quick test
if __name__ == "__main__":
    speak("If you can hear this, blocking SAPI five works for every line.")
