"""
desktop_llama/riva_audio_agent.py
---------------------------------
Asynchronous microphone listener powered by NVIDIA Riva
(Parakeet-1.1B multilingual ASR).  Records until ~0.8 s of silence,
then returns the transcript string.

Usage:
    from desktop_llama.riva_audio_agent import RivaAudioAgent
    mic = RivaAudioAgent()
    text = await mic.listen()
"""

import os, sys, queue, asyncio, sounddevice as sd, webrtcvad, grpc
from dotenv import load_dotenv; load_dotenv()

from riva.client.proto import riva_asr_pb2 as rasr
from riva.client.proto import riva_asr_pb2_grpc as rasr_grpc
import riva.client.proto.riva_audio_pb2 as raudio

# ────────── Riva / NIM credentials ──────────
SERVER_URI  = "grpc.nvcf.nvidia.com:443"
FUNCTION_ID = "71203149-d3b7-4460-8231-1be2543a1fca"
API_KEY     = os.getenv("RIVA_API_KEY")          # export this in your shell
if not API_KEY:
    sys.exit("❌  Please export RIVA_API_KEY with your NGC key")

# ────────── Audio + VAD parameters ──────────
SAMPLE_RATE = 16_000
FRAME_MS    = 30                                 # 30-ms frames
MAX_SILENCE = int(0.8 / (FRAME_MS / 1000))       # ~0.8 s of silence
CHANNELS    = 1
VAD_MODE    = 3                                  # 0 = least, 3 = most aggressive


class RivaAudioAgent:
    """Capture one spoken utterance and transcribe it with Riva."""

    def __init__(self) -> None:
        # Build VAD
        self.vad = webrtcvad.Vad(VAD_MODE)

        # Build gRPC stub once
        creds   = grpc.ssl_channel_credentials()
        channel = grpc.secure_channel(SERVER_URI, creds)
        self.stub = rasr_grpc.RivaSpeechRecognitionStub(channel)

        # RecognitionConfig (note: no language_code field)

        self.rec_config = rasr.RecognitionConfig(
        encoding              = raudio.AudioEncoding.LINEAR_PCM,
        sample_rate_hertz     = SAMPLE_RATE,
        language_code         = "multi",      # ← multi-lingual, auto-detect
        max_alternatives      = 1,
        enable_automatic_punctuation = True,
)


        self.metadata = [
            ("function-id", FUNCTION_ID),
            ("authorization", f"Bearer {API_KEY}"),
        ]

        # Async loop handle
        self.loop = asyncio.get_event_loop()

    # ──────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────
    async def listen(self) -> str:
        """
        Block until the user speaks and then pauses; return transcript.
        """
        return await self.loop.run_in_executor(None, self._record_and_transcribe)

    # ──────────────────────────────────────────────
    # INTERNALS
    # ──────────────────────────────────────────────
    def _record_and_transcribe(self) -> str:
        q = queue.Queue()

        stream = sd.RawInputStream(
            samplerate = SAMPLE_RATE,
            channels   = CHANNELS,
            dtype      = "int16",
            blocksize  = int(SAMPLE_RATE * FRAME_MS / 1000),
            callback   = lambda indata, *args: q.put(bytes(indata)),
        )

        frames, silence = [], 0
        with stream:
            print("🎙  Listening… (speak now)")
            while True:
                frame = q.get()
                if self.vad.is_speech(frame, SAMPLE_RATE):
                    frames.append(frame)
                    silence = 0
                elif frames:
                    silence += 1
                    if silence > MAX_SILENCE:
                        break

        if not frames:
            return ""

        audio_bytes = b"".join(frames)

        # Call Riva offline Recognize
        response = self.stub.Recognize(
            rasr.RecognizeRequest(config=self.rec_config, audio=audio_bytes),
            metadata=self.metadata,
        )

        transcript = " ".join(r.alternatives[0].transcript for r in response.results)
        print(f"🗣  Transcript: {transcript}")
        return transcript.strip()

