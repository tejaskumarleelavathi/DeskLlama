# deskpilot/llama_client.py
#!/usr/bin/env python3
"""
deskpilot.llama_client – async vision+function wrapper
• Returns {"__function_call__":True, "name":..., "arguments":{...}} when the model calls a function.
"""

import atexit, asyncio, base64, hashlib, io, json, os
from typing import AsyncGenerator, Union

import httpx
from PIL import Image
import pytesseract
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("LLAMA_API_KEY")
ENDPOINT = os.getenv("LLAMA_ENDPOINT")
MODEL    = os.getenv("LLAMA_MODEL")
if not all((API_KEY, ENDPOINT, MODEL)):
    raise RuntimeError("Missing LLAMA_API_KEY, LLAMA_ENDPOINT, or LLAMA_MODEL")

# Ensure correct path
_chat = ENDPOINT.rstrip("/")
if not _chat.endswith("/chat/completions"):
    _chat += "/chat/completions"
CHAT_URL = _chat

SYSTEM_TEMPLATE = (
    "You are DeskPilot, an expert desktop assistant.\n"
    "• Summarise in 2–5 sentences.\n"
    "• Use function calls via OpenAI function-calling when helpful.\n"
    "• Never repeat the last reply («{LAST_REPLY}»)."
)

_http: httpx.AsyncClient | None = None
_last_hash: str | None = None

def _jpeg_data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=60, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def _img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()

async def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=60,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
        )
    return _http

async def _post_block(payload: dict) -> dict:
    cli = await _client()
    r = await cli.post(CHAT_URL, json=payload)
    if r.status_code >= 400:
        print("⚠️ Llama API error:", r.text[:500])
    r.raise_for_status()
    return r.json()

async def next_step(
    user_goal: str,
    screenshot: Image.Image,
    prev: str = "",
    last_reply: str = "",
    *,
    stream: bool = False,
    functions: list | None = None,
) -> Union[str, AsyncGenerator[str, None], dict]:
    global _last_hash
    # 1) Resize + decide image send
    screenshot = screenshot.resize((960, 540), Image.LANCZOS)
    h = _img_hash(screenshot)
    send_img = (h != _last_hash)
    _last_hash = h

    # 2) OCR
    try:
        txt = pytesseract.image_to_string(screenshot, lang="eng", config="--psm 6")
    except Exception:
        txt = ""
    if len(txt) > 400:
        txt = ""

    # 3) Build prompt
    system_msg = SYSTEM_TEMPLATE.format(LAST_REPLY=last_reply or "NONE")
    user_blob = f"GOAL: {user_goal}\nPREVIOUS_USER: {prev}\nSCREEN_TEXT: {txt}"
    content = [{"type":"text","text":user_blob}]
    if send_img:
        content.append({"type":"image_url","image_url":{"url":_jpeg_data_uri(screenshot)}})

    payload = {
        "model": MODEL,
        "temperature": 0.25,
        "max_tokens": 256,
        "messages": [
            {"role":"system","content":system_msg},
            {"role":"user","content":content},
        ],
    }
    if functions:
        payload["functions"]     = functions
        payload["function_call"] = "auto"
    # 4) Send
    data = await _post_block(payload)

    # 5) Handle function_call
    choice = data.get("choices", [{}])[0].get("message", {})
    if "function_call" in choice:
        fc = choice["function_call"]
        name = fc["name"]
        try:
            args = json.loads(fc.get("arguments") or "{}")
        except Exception:
            args = {}
        return {"__function_call__": True, "name": name, "arguments": args}

    # 6) Regular reply
    return choice.get("content", "").strip() or "(no reply)"

@atexit.register
def _shutdown():
    global _http
    if _http:
        asyncio.get_event_loop().run_until_complete(_http.aclose())
