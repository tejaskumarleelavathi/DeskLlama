from PIL import Image
import mss

def capture_screen() -> Image.Image:
    """Grab the primary monitor and return a PIL.Image."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]               # 1 = primary
        scr = sct.grab(monitor)
        return Image.frombytes("RGB", scr.size, scr.rgb)
