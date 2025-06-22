# deskpilot/pilot.py
#!/usr/bin/env python3
"""
deskpilot.pilot – voice-first desktop co-pilot.
"""

import asyncio, json, traceback
from deskpilot.llama_client import next_step
from deskpilot.tools         import TOOLS
from deskpilot.actions       import TOOL_FUNCS
from voice_module.riva_agent    import RivaAudioAgent
from voice_module.voice_agent   import speak
from voice_module.screen_capture import capture_screen

async def pilot_loop():
    mic = RivaAudioAgent()
    speak("DeskPilot ready. Say 'quit' to exit.")
    last_reply = ""

    while True:
        try:
            img = capture_screen()
            summary = await next_step(
                "Describe screen + up to 3 follow-up actions in JSON",
                img,
                last_reply=last_reply,
                functions=None,
            )
            # we expect a JSON string
            try:
                parsed = json.loads(summary)
            except:
                parsed = {"screen_summary": summary, "suggestions": []}
            speak(parsed["screen_summary"])
            for i, s in enumerate(parsed["suggestions"],1):
                speak(f"Option {i}: {s['title']}")
            speak("What would you like to do?")

            cmd = await mic.listen()
            if not cmd: continue
            if cmd.lower() in {"quit","exit","goodbye"}:
                speak("Good-bye!"); break

            reply = await next_step(cmd, img, prev=cmd, last_reply=last_reply, functions=TOOLS)
            last_reply = isinstance(reply, str) and reply or str(reply)

            # if function call dict
            if isinstance(reply, dict) and reply.get("__function_call__"):
                name = reply["name"]
                args = reply["arguments"]
                if name in TOOL_FUNCS:
                    try:
                        res = TOOL_FUNCS[name](**args)
                        if asyncio.iscoroutine(res): await res
                        speak("Done.")
                        continue
                    except Exception as e:
                        speak(f"Error: {e}")
            # fallback
            if isinstance(reply, str):
                speak(reply)

        except KeyboardInterrupt:
            speak("Interrupted; shutting down.")
            break
        except Exception as e:
            speak(f"Unexpected error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(pilot_loop())
