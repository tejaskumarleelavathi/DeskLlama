# test_riva_agent.py
import asyncio
from riva_agent import RivaAudioAgent

async def main():
    agent = RivaAudioAgent()           # builds gRPC stub, VAD, etc.
    print("Say something after the beep…")
    text = await agent.listen()        # speak, then pause ~1 s
    print("⇒ Transcript:", text or "(no speech detected)")

if __name__ == "__main__":
    asyncio.run(main())
