# deskpilot/actions.py
"""
deskpilot.actions – implementations for DeskPilot tools.
"""

import asyncio, subprocess, os, shlex
from pathlib import Path
from typing import Optional
import re

import win32com.client as win32  # pip install pywin32

__all__ = ["TOOL_FUNCS"]

# Find Start-Menu shortcuts
_START_DIRS = [
    Path(os.getenv("PROGRAMDATA", r"C:\ProgramData"))/"Microsoft/Windows/Start Menu/Programs",
    Path.home()/"AppData/Roaming/Microsoft/Windows/Start Menu/Programs",
]
_CACHE = {}

def _find_exe(app: str) -> Optional[Path]:
    if app in _CACHE:
        return _CACHE[app]
    pat = re.compile(re.escape(app), re.I)
    for root in _START_DIRS:
        if not root.exists(): continue
        for p in root.rglob("*.lnk"):
            if pat.search(p.stem):
                _CACHE[app] = p; return p
        for p in root.rglob("*.exe"):
            if pat.search(p.stem):
                _CACHE[app] = p; return p
    return None

def open_file_explorer() -> None:
    """Open Windows File Explorer at the user's home directory."""
    home = os.path.expanduser("~")
    subprocess.Popen(["explorer", home], shell=False)

def open_application(app_name: str) -> None:
    """Launch or focus a desktop application by friendly name."""
    exe = _find_exe(app_name)
    if not exe or not exe.exists():
        raise RuntimeError(f"Cannot find application '{app_name}'.")
    subprocess.Popen(shlex.split(f'"{exe}"'), shell=False)

async def send_email(to: str, subject: str, body: str) -> None:
    """Send an email via Outlook."""
    outlook = win32.Dispatch("Outlook.Application")
    mail    = outlook.CreateItem(0)
    mail.To, mail.Subject, mail.Body = to, subject, body
    mail.Send()
    await asyncio.sleep(0.5)

TOOL_FUNCS = {
    "open_file_explorer": open_file_explorer,
    "open_application":   open_application,
    "send_email":         send_email,
}
