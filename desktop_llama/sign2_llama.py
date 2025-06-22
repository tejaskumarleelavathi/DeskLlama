#!/usr/bin/env python
"""
sign2text_llama4.py  –  live ASL sentence ➜ text via Llama-4 vision

.env MUST contain
  LLAMA_ENDPOINT=https://api.your-provider.com/v1/chat/completions
  LLAMA_API_KEY=sk-...
  LLAMA_MODEL=llama-4-vision         # or gpt-4o-mini-vision, etc.
"""

import os, cv2, base64, time, asyncio, threading, requests, numpy as np
from dotenv import load_dotenv
load_dotenv()

# ── env & sanity check ───────────────────────────────────────────────
EP   = os.getenv("LLAMA_ENDPOINT")
KEY  = os.getenv("LLAMA_API_KEY")
MODEL= os.getenv("LLAMA_MODEL")
if not (EP and KEY and MODEL):
    raise RuntimeError("❌  Missing LLAMA_ENDPOINT / LLAMA_API_KEY / LLAMA_MODEL in .env")

HEADERS = {"Authorization": f"Bearer {KEY}",
           "Content-Type": "application/json"}

PROMPT = ("You are an ASL interpreter. Transcribe the signer’s sentence into "
          "concise English. Respond ONLY with the transcription.")

FRAMES   = 8           # 8 frames ~ 3 s
INTERVAL = 0.4         # seconds between frames
MOTION_TH = 8.0        # simple motion trigger (average pixel diff)

# ── helpers ──────────────────────────────────────────────────────────
def to_data_uri(frame: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()

def ask_llama(image_uris):
    body = {
        "model": MODEL,
        "temperature": 0.2,
        "max_tokens": 60,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": PROMPT}, *image_uris]
        }]
    }
    r = requests.post(EP, headers=HEADERS, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["completion_message"]["content"]["text"].strip()

# ── async queue for results ──────────────────────────────────────────
queue: asyncio.Queue[str] = asyncio.Queue()

def capture_worker(loop: asyncio.AbstractEventLoop):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # DirectShow backend
    if not cap.isOpened():
        loop.call_soon_threadsafe(queue.put_nowait,
                                  "[ERR] Webcam not available"); return

    prev = None
    try:
        while True:
            # Wait for motion
            ret, prev = cap.read()
            if not ret: break
            while True:
                ret, frm = cap.read()
                if not ret: break
                if np.mean(cv2.absdiff(prev, frm)) > MOTION_TH:
                    break
                prev = frm
                cv2.waitKey(33)

            # Capture clip
            clip = []
            for _ in range(FRAMES):
                ret, frm = cap.read(); clip.append(frm)
                cv2.waitKey(int(INTERVAL * 1000))

            uris = [{"type": "image_url",
                     "image_url": {"url": to_data_uri(f), "detail": "high"}}
                    for f in clip]
            try:
                text = ask_llama(uris)
            except Exception as e:
                text = f"[ERR] {e}"
            loop.call_soon_threadsafe(queue.put_nowait, text)
    finally:
        cap.release()

# ── main async loop ──────────────────────────────────────────────────
async def main():
    loop = asyncio.get_running_loop()
    threading.Thread(target=capture_worker, args=(loop,), daemon=True).start()
    print("Sign-to-Text started. Sign a sentence; pause ~1 s; transcription prints.")
    try:
        while True:
            txt = await queue.get()
            print("\n📝", txt)
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
