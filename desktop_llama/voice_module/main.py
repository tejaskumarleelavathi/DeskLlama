
#!/usr/bin/env python3
"""
desktop_llama/main.py
---------------------
Desktop assistant driven by NVIDIA Riva (streaming ASR) +
Llama-4 vision.  One question → one answer.

• Listens for speech, grabs a screenshot, sends both to next_step().
• Says the reply with Magpie TTS (and prints it for debugging).
• “exit / quit / bye …” ends the program.
"""

import asyncio, re
from dotenv import load_dotenv; load_dotenv()

from voice_module.riva_agent     import RivaAudioAgent
from voice_module.screen_capture import capture_screen
from voice_module.llama_client   import next_step        # async vision call
from voice_module.voice_agent    import speak as _speak
from voice_module.camera_agent   import describe_selfie

# — utility wrapper so the reply is also echoed to the terminal — #
def speak(text: str, *, _echo: bool = True) -> None:
    if _echo:
        print(f"[Assistant] {text}")
    _speak(text)

BREAK_WORDS = {"exit", "quit", "bye", "goodbye", "stop assistant"}

# ──────────────────────────────────────────────────────────────── #
async def main() -> None:
    # greet with optional selfie description
    try:
        greeting = await asyncio.to_thread(describe_selfie)
        speak(greeting)
    except Exception as e:
        print("[Selfie greeting failed]", e)

    speak("What would you like me to do?")

    mic          = RivaAudioAgent()   # Parakeet streaming ASR
    prev, last   = "", ""             # short conversation memory

    while True:
        # — listen for user utterance —
        goal = (await mic.listen()).strip()
        if not goal:
            continue
        if any(w in goal.lower() for w in BREAK_WORDS):
            speak("Goodbye!")
            break

        # — get screenshot & ask Llama —
        img     = capture_screen()
        answer  = await next_step(goal, img, prev, last)

        # simple anti-repeat guard
        if answer.lower() == last.lower():
            prev += " (DON'T REPEAT.)"
            answer = await next_step(goal, img, prev, last)

        speak(answer)
        last  = answer
        prev += f" USER: {goal}"

# ──────────────────────────────────────────────────────────────── #
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        speak("Assistant stopped. Goodbye!")
