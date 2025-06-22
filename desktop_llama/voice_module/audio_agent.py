"""
VAD streaming microphone → Whisper transcript (English only).
"""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"   # avoid Intel OpenMP clash

import asyncio, wave, queue, threading
from tempfile import NamedTemporaryFile

import sounddevice as sd
import webrtcvad
from faster_whisper import WhisperModel

class AudioAgent:
    SAMPLE_RATE = 16_000
    FRAME_MS = 30
    MAX_SILENCE = int(0.8 / (FRAME_MS / 1000))
    def __init__(self, model_size="base"):
        self.model = WhisperModel(model_size, cpu_threads=4)
        self.vad   = webrtcvad.Vad(3)
        self.loop  = asyncio.get_event_loop()

    async def listen(self) -> str:
        return await self.loop.run_in_executor(None, self._record_and_transcribe)

    def _record_and_transcribe(self) -> str:
        q = queue.Queue()
        rec = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=int(self.SAMPLE_RATE * self.FRAME_MS / 1000),
            callback=lambda indata, *args: q.put(bytes(indata)),
        )
        frames, silence = [], 0
        with rec:
            print("🎙️  Listening… (speak now)")
            while True:
                frame = q.get()
                if self.vad.is_speech(frame, self.SAMPLE_RATE):
                    frames.append(frame); silence = 0
                elif frames:
                    silence += 1
                    if silence > self.MAX_SILENCE:
                        break
        path = NamedTemporaryFile(delete=False, suffix=".wav").name
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        segments, _ = self.model.transcribe(path, language="en")
        os.unlink(path)
        text = " ".join(seg.text.strip() for seg in segments)
        print(f"🗣️  Whisper transcript: {text}")
        return text.strip()
