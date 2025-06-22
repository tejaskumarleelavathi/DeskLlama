

#!/usr/bin/env python3
"""
faster_vision_client.py  –  async + streaming (single-mode)
-----------------------------------------------------------
• JPEG-compresses screenshot at 960 × 540 (≈60 kB).
• Sends image **only if screen hash changed** since last call.
• OCR runs on *every* request (short-circuits if >400 chars).
• Uses **httpx.AsyncClient** with keep-alive; supports streaming tokens.

API
---
* `reply = await next_step(goal, img)` – blocking, returns final string.
* `async for tok in next_step(goal, img, stream=True): ...` – get tokens.
"""
from __future__ import annotations
import atexit, asyncio, os, io, base64, hashlib, json
from typing import AsyncGenerator, Union

import httpx
from PIL import Image
import pytesseract
from dotenv import load_dotenv; load_dotenv()

LLAMA_KEY  = os.getenv("LLAMA_API_KEY")
ENDPOINT   = os.getenv("LLAMA_ENDPOINT")
MODEL      = os.getenv("LLAMA_MODEL")

SYSTEM = """
You are DeskLlama, a voice-controlled desktop helper.

• Always be helpful and specific. Summarise answers in 2-5 concise
  sentences **and** mention anything relevant you can infer from
  the current screen when helpful.

• Never repeat LAST_REPLY («{LAST_REPLY}»).
"""

# ── globals ---------------------------------------------------------
_http: httpx.AsyncClient | None = None
_last_hash: str | None = None

# ── helpers ---------------------------------------------------------
def _data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def _img_hash(img: Image.Image) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()

async def _http_client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=60,
            headers={
                "Authorization": f"Bearer {LLAMA_KEY}",
                "Content-Type": "application/json",
            },
        )
    return _http

async def _post_block(json_payload: dict) -> dict:
    cli = await _http_client()
    r = await cli.post(ENDPOINT, json=json_payload)
    r.raise_for_status()
    return r.json()

async def _post_stream(json_payload: dict) -> AsyncGenerator[str, None]:
    json_payload["stream"] = True
    cli = await _http_client()
    async with cli.stream("POST", ENDPOINT, json=json_payload) as r:
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj.get("delta") or obj.get("choices", [{}])[0].get("delta", {})
                if (content := delta.get("content")):
                    yield content
            except json.JSONDecodeError:
                continue

# ── public async API ------------------------------------------------
async def next_step(
    user_goal: str,
    screenshot: Image.Image,
    prev: str = "",
    last_reply: str = "",
    *,
    stream: bool = False,
    tools=None
) -> Union[str, AsyncGenerator[str, None]]:
    """
    Blocking or streaming vision call to Llama.

    • stream=False → await -> str
    • stream=True  → returns AsyncGenerator yielding str tokens
    """
    global _last_hash

    screenshot = screenshot.resize((960, 540), Image.LANCZOS)
    img_h = _img_hash(screenshot)
    send_image = img_h != _last_hash
    _last_hash = img_h

    # OCR every time (trim if huge)
    screen_txt = ""
    try:
        screen_txt = pytesseract.image_to_string(
            screenshot, lang="eng", config="--psm 6"
        )
    except pytesseract.TesseractNotFoundError:
        pass
    if len(screen_txt) > 400:
        screen_txt = ""

    prompt = SYSTEM.replace("{LAST_REPLY}", last_reply or "NONE")
    user_blob = (
        f"{prompt}\nGOAL: {user_goal}\nPREVIOUS_USER: {prev}\nSCREEN_TEXT: {screen_txt}"
    )

    content = [{"type": "text", "text": user_blob}]
    if send_image:
        content.append({"type": "image_url", "image_url": {"url": _data_uri(screenshot)}})

    payload = {
        "model": MODEL,
        "temperature": 0.3,
        "max_tokens": 120,
        "messages": [{"role": "user", "content": content}],
    }

    if stream:
        return _post_stream(payload)

    if tools:
        payload.update({"tools": tools, "tool_choice": "auto"})

    data = await _post_block(payload)
    try:
        return data["completion_message"]["content"]["text"].strip()
    except Exception:
        return "Sorry—I couldn’t parse Llama’s reply."

# ── graceful shutdown ----------------------------------------------
@atexit.register
def _close() -> None:
    """Close the shared httpx.AsyncClient without throwing tracebacks."""
    if _http is None or _http.is_closed:
        return

    async def _do_close():
        try:
            await _http.aclose()
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_do_close())
        else:
            loop.run_until_complete(_do_close())
    except RuntimeError:
        asyncio.run(_do_close())
