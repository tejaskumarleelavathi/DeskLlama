import cv2, base64, os, requests, numpy as np
from dotenv import load_dotenv; load_dotenv()

EP, KEY, MODEL = os.getenv("LLAMA_ENDPOINT"), os.getenv("LLAMA_API_KEY"), os.getenv("LLAMA_MODEL")
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}




PROMPT = (
    "You’re a cheerful AI meeting the user via webcam. "
    'Respond with exactly **one** sentence of **20 words or fewer** that begins with: '
    '"Hi! I\'m your desktop assistant. Nice to meet you." '
    "After that greeting, briefly describe the user’s outfit and visible mood, turning both into a warm compliment."
)

def _data_uri(frame, size=512):
    h, w = frame.shape[:2]
    frame = cv2.resize(frame, (int(w*size/max(h,w)), int(h*size/max(h,w))))
    _, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()

def describe_selfie() -> str:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_CONVERT_RGB, 1.0)         # needs float, not bool
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return "I couldn't access the webcam, but I bet you look great today!"

    body = {
        "model": MODEL,
        "temperature": 0.4,
        "max_tokens": 60,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": _data_uri(frame), "detail": "high"}}
            ]}
        ]
    }
    r = requests.post(EP, headers=HEADERS, json=body, timeout=90)
    r.raise_for_status()
    return r.json()["completion_message"]["content"]["text"].strip()
