# #!/usr/bin/env python3
"""
desktop_llama/text_main.py
--------------------------
Keyboard-only version of DeskLlama (no mic, no TTS).

• Grabs a screenshot each turn so the model can “see” your screen.
• Keeps a short conversation history to avoid repetition.
• Type “exit / quit / bye” (or hit Ctrl-C / Ctrl-D) to leave.
"""

import asyncio, re, sys
from pathlib import Path
from dotenv import load_dotenv; load_dotenv()

from voice_module.screen_capture import capture_screen      # screenshot
from voice_module.llama_client   import next_step           # async vision call
from voice_module.camera_agent   import describe_selfie     # optional selfie

BREAK_WORDS = {"exit", "quit", "bye", "goodbye", "stop"}
ENABLE_SCREENSHOT = True       # flip to False if running head-less

# ── main async loop ────────────────────────────────────────────────
async def main() -> None:
    prev, last = "", ""        # running history + last answer

    # Optional “hello” that uses your webcam
    try:
        print("Assistant> Let me take a quick look…")
        hello_line = await asyncio.to_thread(describe_selfie)
        print(f"Assistant> {hello_line}")
    except Exception as e:
        print(f"[Selfie greeting failed] {e}")

    print("DeskLlama ready. Type your question (exit to quit).")

    while True:
        # ── read user input ────────────────────────────────────────
        try:
            goal = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAssistant> Goodbye!")
            break

        if not goal:
            continue
        if any(w in goal.lower() for w in BREAK_WORDS):
            print("Assistant> Goodbye!")
            break

        # ── ask the model ─────────────────────────────────────────
        img = capture_screen() if ENABLE_SCREENSHOT else None
        answer = await next_step(goal, img, prev, last)

        # crude anti-repeat guard
        if answer.lower() == last.lower():
            prev += " (DON'T REPEAT.)"
            answer = await next_step(goal, img, prev, last)

        print(f"Assistant> {answer}")
        last = answer
        prev += f" USER: {goal}"

        # model sometimes ends with “Anything else?”
        if re.search(r"(goal|task) complete|anything else", answer, re.I):
            continue

# ── entry-point ───────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
