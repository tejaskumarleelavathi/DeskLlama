"""
VAD microphone ➜ Riva Parakeet-1.1B transcript
----------------------------------------------
• Records until 0.8 s of silence is detected.
• Sends the whole utterance to Riva ASR (offline Recognize).
• Works on Windows / macOS / Linux.
"""

import os, queue, asyncio, sounddevice as sd, webrtcvad, grpc, sys
from riva.client.proto import riva_asr_pb2 as rasr
from riva.client.proto import riva_asr_pb2_grpc as rasr_grpc
import riva.client.proto.riva_audio_pb2 as raudio
from dotenv import load_dotenv; load_dotenv()


# ────────── Riva / NIM credentials ──────────
SERVER_URI  = os.getenv("RIVA_ENDPOINT")
FUNCTION_ID = os.getenv("RIVA_FUNCTION_ID")
API_KEY     = os.getenv("RIVA_API_KEY")        # export first!
LANG_CODE   = "en-US"

if not API_KEY:
    sys.exit("❌  Set RIVA_API_KEY env-var with your NGC key")

# ────────── Audio + VAD parameters ──────────
SAMPLE_RATE   = 16_000
FRAME_MS      = 30
MAX_SILENCE   = int(0.8 / (FRAME_MS / 1000))   # 0.8 s worth of frames
CHANNELS      = 1

# ────────── Build gRPC stub ──────────
creds   = grpc.ssl_channel_credentials()
channel = grpc.secure_channel(SERVER_URI, creds)
stub    = rasr_grpc.RivaSpeechRecognitionStub(channel)

rec_config = rasr.RecognitionConfig(
    encoding              = raudio.AudioEncoding.LINEAR_PCM,
    sample_rate_hertz     = SAMPLE_RATE,
    language_code         = LANG_CODE,
    max_alternatives      = 1,
    enable_automatic_punctuation = True,
)

metadata = [
    ("function-id", FUNCTION_ID),
    ("authorization", f"Bearer {API_KEY}"),
]

vad  = webrtcvad.Vad(3)         # 0–3; 3 = most aggressive
loop = asyncio.get_event_loop()

async def listen() -> str:
    return await loop.run_in_executor(None, record_and_transcribe)

def record_and_transcribe() -> str:
    q = queue.Queue()
    stream = sd.RawInputStream(                    # raw bytes
        samplerate = SAMPLE_RATE,
        channels   = CHANNELS,
        dtype      = "int16",
        blocksize  = int(SAMPLE_RATE * FRAME_MS / 1000),
        callback   = lambda indata, *args: q.put(bytes(indata)),
    )

    frames, silence = [], 0
    with stream:
        print("🎙️  Listening… (speak now, Ctrl-C to quit)")
        while True:
            frame = q.get()
            if vad.is_speech(frame, SAMPLE_RATE):
                frames.append(frame)
                silence = 0
            elif frames:
                silence += 1
                if silence > MAX_SILENCE:
                    break

    audio_bytes = b"".join(frames)

    # ───── Call Riva offline Recognize ─────
    response = stub.Recognize(
        rasr.RecognizeRequest(config=rec_config, audio=audio_bytes),
        metadata = metadata,
    )

    transcript = " ".join(res.alternatives[0].transcript for res in response.results)
    print(f"🗣️  Riva transcript: {transcript}")
    return transcript.strip()

# ────────── Run once ──────────
if __name__ == "__main__":
    try:
        loop.run_until_complete(listen())
    except KeyboardInterrupt:
        print("\n🛑  Stopped.")
