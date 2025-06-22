#!/usr/bin/env python
"""
describe_and_compliment_camera.py  –  live webcam ➜ friendly description + compliment

.env MUST contain
  LLAMA_ENDPOINT=https://api.your-provider.com/v1/chat/completions
  LLAMA_API_KEY=sk-...
  LLAMA_MODEL=llama-4-vision       # or gpt-4o-mini-vision, etc.

Run the script, look into the camera, and pause for a moment.
Whenever motion is detected, the current frame is sent to Llama 4 Vision,
which returns a short user description plus a genuine compliment.
"""

import os, cv2, base64, time, asyncio, threading, requests, numpy as np
from dotenv import load_dotenv
load_dotenv()

# ── env & sanity check ───────────────────────────────────────────────
KEY = "LLM|1372040663912747|WL399woTt93BFgbwrnuu7no646g"
EP = "https://api.llama.com/v1/chat/completions"
MODEL = "Llama-4-Scout-17B-16E-Instruct-FP8"
if not (EP and KEY and MODEL):
    raise RuntimeError("❌  Missing LLAMA_ENDPOINT / LLAMA_API_KEY / LLAMA_MODEL in .env")

HEADERS = {"Authorization": f"Bearer {KEY}",
           "Content-Type": "application/json"}

PROMPT = ("You're a friendly assistant meeting the user via webcam. "
          "Briefly describe what you see (e.g., clothing, mood) and "
          "finish with a warm, sincere compliment. Keep it under 40 words. "
          "Respond ONLY with that single friendly sentence.")

INTERVAL    = 0.3         # seconds between motion checks
MOTION_TH   = 6.0         # motion trigger threshold (avg pixel diff)
FRAME_SIZE  = 512         # long‑edge resize before JPEG/base64

# ── helpers ──────────────────────────────────────────────────────────
def to_data_uri(frame: np.ndarray) -> str:
    h, w = frame.shape[:2]
    scale = FRAME_SIZE / max(h, w)
    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    _, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()

def ask_llama(image_uri: str) -> str:
    body = {
        "model": MODEL,
        "temperature": 0.4,
        "max_tokens": 60,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": image_uri, "detail": "high"}}]
        }]
    }
    r = requests.post(EP, headers=HEADERS, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["completion_message"]["content"]["text"].strip()

# ── async queue for results ──────────────────────────────────────────
queue: asyncio.Queue[str] = asyncio.Queue()

def capture_worker(loop: asyncio.AbstractEventLoop):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        loop.call_soon_threadsafe(queue.put_nowait,
                                  "[ERR] Webcam not available"); return

    # Ensure frames are RGB; some builds need float 1.0, not bool
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 1.0)

    ret, prev = cap.read()
    if not ret:
        loop.call_soon_threadsafe(queue.put_nowait,
                                  "[ERR] Could not read from camera")
        cap.release()
        return

    try:
        while True:
            ret, frm = cap.read()
            if not ret: break
            # simple motion detection
            if np.mean(cv2.absdiff(prev, frm)) > MOTION_TH:
                uri = to_data_uri(frm)
                try:
                    text = ask_llama(uri)
                except Exception as e:
                    text = f"[ERR] {e}"
                loop.call_soon_threadsafe(queue.put_nowait, text)
                time.sleep(1.5)  # debounce to avoid spamming
            prev = frm
            cv2.waitKey(int(INTERVAL*1000))
    finally:
        cap.release()

# ── main async loop ──────────────────────────────────────────────────
async def main():
    loop = asyncio.get_running_loop()
    threading.Thread(target=capture_worker, args=(loop,), daemon=True).start()
    print("Describe‑and‑Compliment started. Look at the camera and pause for a compliment.")
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
