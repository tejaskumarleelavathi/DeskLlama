#!/usr/bin/env python
"""
mic_to_a2f_fixed.py – records mic, patches YAML header so it ALWAYS matches,
streams to Audio2Face-3D, writes blendshapes.csv
"""

import os, csv, wave, tempfile, asyncio, sys, pathlib, yaml, numpy as np, sounddevice as sd
from dotenv import load_dotenv; load_dotenv()

# ── choose ONE sample-rate here ------------------------------------------------
RATE      = 48_000          # ← set to 22_050 if you really want 22 kHz
CHANNELS  = 1
SECONDS   = 5
# ------------------------------------------------------------------------------

# locate helper package
ROOT = pathlib.Path(__file__).resolve().parent
CLIENT_DIR = (ROOT / "Audio2Face-3D-Samples" / "scripts" / "audio2face_3d_api_client").resolve()
sys.path.append(str(CLIENT_DIR))

import a2f_3d.client.auth as a2f_auth
import a2f_3d.client.service as a2f_srv
from nvidia_ace.services.a2f_controller.v1_pb2_grpc import A2FControllerServiceStub

CFG_SRC = CLIENT_DIR / "config" / "config_mark.yml"   # neutral Mark config

SERVER      = "grpc.nvcf.nvidia.com:443"
API_KEY     = "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"
FUNC_ID = "8efc55f5-6f00-424e-afe9-26212cd2c630"
if not (API_KEY and FUNC_ID):
    sys.exit("Set A2F_API_KEY and A2F_FUNCTION_ID env vars first.")

# patch YAML so header ALWAYS matches the recorder -----------------------------
def patched_yaml(src: pathlib.Path) -> str:
    data = yaml.safe_load(src.read_text())
    data["audio_header"] = {
        "sample_rate_hz": RATE,
        "bit_depth": 16,
        "num_channels": CHANNELS,
    }
    tmp = pathlib.Path(tempfile.mkstemp(suffix=".yml")[1])
    tmp.write_text(yaml.safe_dump(data))
    return str(tmp)

CFG_FILE = patched_yaml(CFG_SRC)
print("⚙️  Sending header :", yaml.safe_load(pathlib.Path(CFG_FILE).read_text())["audio_header"])

# record mic → 16-bit PCM WAV ---------------------------------------------------
wav_path = tempfile.mktemp(suffix=".wav")
print(f"🔴  Recording {SECONDS}s @ {RATE//1000} kHz …")
pcm = sd.rec(int(SECONDS * RATE), samplerate=RATE, channels=CHANNELS, dtype=np.int16)
sd.wait()
with wave.open(wav_path, "wb") as w:
    w.setnchannels(CHANNELS); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(pcm.tobytes())
print("✅  WAV saved:", wav_path)

# async stream -----------------------------------------------------------------
async def main():
    meta = [("function-id", FUNC_ID), ("authorization", f"Bearer {API_KEY}")]
    chan = a2f_auth.create_channel(uri=SERVER, use_ssl=True, metadata=meta)
    stub = A2FControllerServiceStub(chan)

    stream = stub.ProcessAudioStream()
    t_w = asyncio.create_task(a2f_srv.write_to_stream(stream, CFG_FILE, wav_path))
    t_r = asyncio.create_task(a2f_srv.read_from_stream(stream))

    await t_w
    result = await t_r
    if result is None:
        sys.exit("❌  Still rejected – double-check Windows sound settings are 16-bit.")

    frames, names = result
    with open("blendshapes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time_sec", *names])
        for fr in frames:
            w.writerow([fr.time_stamp, *fr.values])
    print("💾  Saved", len(frames), "frames → blendshapes.csv")

if __name__ == "__main__":
    asyncio.run(main())
