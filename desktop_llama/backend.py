"""
Shared core logic for Desk Llama.

✓ One-shot text/vision request  ->  await DeskLlamaCore.ask(prompt)
✓ Continuous speech loop        ->  await DeskLlamaCore.speech_loop(cancel_evt)
"""

import asyncio
from pathlib import Path

# --- your existing helpers ---------------------------------------------------
from desktop_llama.voice_module.riva_agent     import RivaAudioAgent
from desktop_llama.voice_module.screen_capture import capture_screen
from desktop_llama.voice_module.llama_client   import next_step
from desktop_llama.voice_module.voice_agent    import speak as tts
# -----------------------------------------------------------------------------



BREAK_WORDS = {"exit", "quit", "bye", "goodbye", "stop assistant"}


class DeskLlamaCore:
    def __init__(self):
        self.history: str = ""          # running chat context
        self.last_answer: str = ""

    # ──────────────────────────────────────────────────────────────────────────
    async def ask(self, user_text: str) -> str:
        """Send text + current screen to the Llama backend and return reply."""
        screenshot = capture_screen()           # numpy array
        reply = await next_step(user_text,
                                screenshot,
                                self.history,
                                self.last_answer)

        self.history += f"\nUSER: {user_text}"
        self.last_answer = reply
        return reply

    # ──────────────────────────────────────────────────────────────────────────



    async def speech_loop(self, cancel_event: asyncio.Event):
        mic = RivaAudioAgent()
        print("🔈 Speech loop started")
        try:
            while not cancel_event.is_set():
                utterance = (await mic.listen()).strip()
                if not utterance:
                    continue

                if any(w in utterance.lower() for w in BREAK_WORDS):
                    tts("Good-bye!")
                    cancel_event.set()
                    break

                reply = await self.ask(utterance)
                tts(reply)

        except asyncio.CancelledError:
            # task was cancelled (e.g. Esc or mic toggle) — just exit
            pass

        finally:
            # RivaAudioAgent in your codebase has no stop(); guard it.
            if hasattr(mic, "stop"):
                mic.stop()
            elif hasattr(mic, "close"):
                mic.close()
            print("🔇 Speech loop terminated")
