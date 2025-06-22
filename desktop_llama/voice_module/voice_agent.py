
"""
voice_output_riva_stream.py
---------------------------
Low-latency Magpie-TTS (Riva NIM) – now with an “Esc to stop” hotkey.

• Press Esc during playback → audio stops instantly and control returns to the
  listening loop.
• Works on Windows/macOS/Linux (on Linux you may need sudo for global hotkeys).
"""

import os, sys, threading, atexit, sounddevice as sd, numpy as np, grpc
from dotenv import load_dotenv; load_dotenv()

# ── NEW: global flag + keyboard watcher ──────────────────────────────
import keyboard        # pip install keyboard
_stop_tts = threading.Event()

def _watch_keyboard():
    """Block until Esc is pressed, then signal all audio threads to stop."""
    try:
        keyboard.wait('space')
    except KeyError:
        # hot-key already removed – ignore
        pass
    _stop_tts.set()

# ── Riva stubs ───────────────────────────────────────────────────────
try:
    from riva.client.proto import riva_tts_pb2 as rtts
    from riva.client.proto import riva_tts_pb2_grpc as rtts_grpc
    import riva.client.proto.riva_audio_pb2 as raudio
    _have_riva = True
except ImportError:
    _have_riva = False

# ── CONFIG ───────────────────────────────────────────────────────────
SERVER_URI  = "grpc.nvcf.nvidia.com:443"
FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"         # magpie-tts-multilingual
API_KEY     = os.getenv("RIVA_API_KEY")
LANG_CODE   = "en-US"
VOICE_NAME  = "Magpie-Multilingual.EN-US.Sofia"
SAMPLE_RATE = 22_050
ENCODING    = raudio.AudioEncoding.LINEAR_PCM

# ── build Riva stub once ─────────────────────────────────────────────
_stub = None
if _have_riva and API_KEY:
    try:
        _stub = rtts_grpc.RivaSpeechSynthesisStub(
            grpc.secure_channel(SERVER_URI, grpc.ssl_channel_credentials()))
    except Exception as e:
        print("[TTS] Riva init failed – will fall back:", e, file=sys.stderr)

# ── local fallback (pyttsx3) ─────────────────────────────────────────
_lock = threading.Lock()
try:
    import pyttsx3
    _local = pyttsx3.init("sapi5")
    for v in _local.getProperty("voices"):
        if any(k in v.name.lower() for k in ("sofia", "aria", "jenny",
                                             "david", "guy", "mason")):
            _local.setProperty("voice", v.id); break
    _local.setProperty("rate", 185)
    atexit.register(_local.stop)
except Exception:
    _local = None

# ── fast streaming TTS (Riva) ────────────────────────────────────────
def _speak_riva(text: str) -> bool:
    if not _stub:
        return False
    try:
        req = rtts.SynthesizeSpeechRequest(
            text=text,
            language_code=LANG_CODE,
            voice_name=VOICE_NAME,
            sample_rate_hz=SAMPLE_RATE,
            encoding=ENCODING,
        )
        md = [("function-id", FUNCTION_ID),
              ("authorization", f"Bearer {API_KEY}")]

        stream = _stub.SynthesizeOnline(req, metadata=md)

        with _lock, sd.RawOutputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16") as out:

            for resp in stream:
                if _stop_tts.is_set():            # <-- check for Esc
                    break
                if resp.audio:
                    out.write(resp.audio)
                if _stop_tts.is_set():
                    break

            # flush any queued samples if we weren’t stopped by Esc
            if not _stop_tts.is_set():
                silence_tail = (np.zeros(int(0.05 * SAMPLE_RATE))
                                .astype(np.int16).tobytes())   # 50 ms
                out.write(silence_tail)
                out.stop()
        if not _stop_tts.is_set():
            sd.wait()
        return not _stop_tts.is_set()
    except Exception as e:
        print("[TTS] Riva stream failed – falling back:", e, file=sys.stderr)
        return False

# ── local fallback (pyttsx3) ─────────────────────────────────────────
def _speak_local(text: str):
    if not _local:
        print("Assistant:", text); return
    print("Assistant:", text)
    with _lock:
        try:
            if _stop_tts.is_set():        # Esc hit before fallback starts
                return
            _local.say(text)
            _local.runAndWait()
        except Exception as e:
            print("[TTS error]", e, file=sys.stderr)

# ── public API ───────────────────────────────────────────────────────
def speak(text: str) -> None:
    """
    Print & speak; press Esc to interrupt.
    Riva first, pyttsx3 fallback.
    """
    # reset & start keyboard watcher
    _stop_tts.clear()
    watcher = threading.Thread(target=_watch_keyboard, daemon=True)
    watcher.start()

    try:
        played = _speak_riva(text)
        if not played and not _stop_tts.is_set():
            _speak_local(text)
    finally:
        _stop_tts.set()           # ensure watcher thread exits

# ── quick test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Press Esc at any time to interrupt.")
    speak("If you hear this entire sentence without interruption, the \
streaming Magpie TTS is working. But you can press escape to stop me \
mid-sentence whenever you like.")