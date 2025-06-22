# windows_overlay.py
"""
Foreground-window numbered overlay (dynamic)
===========================================
Numbers **only** controls in the **active (foreground) window**, updates
whenever you Alt-Tab or the window’s UI changes, and keeps the numbering tight
(starting at 1 for the first clickable element it sees on that window).

Quick start
~~~~~~~~~~~
::

    pip install uiautomation PyQt6
    Start-Process powershell -Verb runAs
    python windows_overlay.py

How it works
~~~~~~~~~~~~
* A lightweight timer checks every 500 ms; if the foreground window has changed
  (handle or title) we rescan + renumber.
* Overlay is clipped to the window’s bounding rect instead of the whole screen.
* Clicks use UIA `InvokePattern` if available, falling back to a synthetic
  mouse click centred on the control.
"""
from __future__ import annotations

import sys, time
from dataclasses import dataclass
from typing import List

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    import uiautomation as auto  # pip install uiautomation
except ImportError:
    print("✖  uiautomation not installed – run `pip install uiautomation`.\n"); sys.exit(1)

###############################################################################
# Data model                                                                   #
###############################################################################

@dataclass
class UIElement:
    number: int
    ctrl:   auto.Control

    @property
    def rect(self) -> QtCore.QRectF:  # QRectF(x, y, w, h) in screen-coords
        br = self.ctrl.BoundingRectangle
        return QtCore.QRectF(br.left, br.top, br.right - br.left, br.bottom - br.top)

    @property
    def role(self) -> str:
        return self.ctrl.ControlTypeName or "Unknown"

###############################################################################
# Scanner – only the foreground window                                         #
###############################################################################

INTERACTIVE_CTYPES = {
    "ButtonControl", "EditControl", "ComboBoxControl", "HyperlinkControl",
    "ListItemControl", "MenuItemControl", "RadioButtonControl",
    "CheckBoxControl", "SliderControl", "TabItemControl"
}

class ForegroundScanner:
    """Return UIElements for interactive controls in the active window."""

    def __init__(self):
        self.last_handle: int | None = None
        self.last_title:  str | None = None

    # --------------------------------------------------------------- utils ---
    @staticmethod
    def _walk(root: auto.Control, bucket: List[auto.Control]):
        if root.ControlTypeName in INTERACTIVE_CTYPES and root.BoundingRectangle:
            bucket.append(root)
        for ch in root.GetChildren():
            ForegroundScanner._walk(ch, bucket)

    # --------------------------------------------------------------- api  ---
    def scan(self) -> tuple[List[UIElement], QtCore.QRect]:
        win = auto.GetForegroundControl()
        if not win:
            return [], QtCore.QRect()

        changed = (win.NativeWindowHandle != self.last_handle or
                    win.Name != self.last_title)
        self.last_handle = win.NativeWindowHandle
        self.last_title  = win.Name

        bucket: List[auto.Control] = []
        ForegroundScanner._walk(win, bucket)

        # Sort bottom-to-top then left-to-right for stable visual numbering
        bucket.sort(key=lambda c: (-c.BoundingRectangle.top, c.BoundingRectangle.left))
        elements = [UIElement(i + 1, c) for i, c in enumerate(bucket)]

        br = win.BoundingRectangle
        win_rect = QtCore.QRect(br.left, br.top, br.right - br.left, br.bottom - br.top)
        return elements, win_rect

###############################################################################
# Badge widget                                                                 #
###############################################################################

ROLE_COLORS = {
    "ButtonControl": QtGui.QColor(0, 122, 255, 200),
    "EditControl":   QtGui.QColor(52, 199, 89, 200),
    "HyperlinkControl": QtGui.QColor(175, 82, 222, 200),
}
DEFAULT_BG = QtGui.QColor(0, 0, 0, 180)
BORDER     = QtGui.QColor(255, 255, 255, 90)

class Badge(QtWidgets.QLabel):
    def __init__(self, elem: UIElement, parent: QtWidgets.QWidget):
        super().__init__(str(elem.number), parent)
        self.elem = elem
        self.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Weight.DemiBold))
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        fm = QtGui.QFontMetrics(self.font())
        w = fm.horizontalAdvance(self.text()) + 20
        h = fm.height() + 8
        self.resize(w, h)

        # place badge slightly up/left of control rect
        r = elem.rect
        self.move(int(r.x()) - 14, int(r.y()) - 14)

    def paintEvent(self, _) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setBrush(ROLE_COLORS.get(self.elem.role, DEFAULT_BG))
        p.setPen(QtGui.QPen(BORDER, 0.7))
        p.drawRoundedRect(self.rect(), 6, 6)
        p.setPen(QtGui.QColor("white"))
        p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, self.text())

###############################################################################
# Overlay window                                                               #
###############################################################################

class Overlay(QtWidgets.QWidget):
    def __init__(self, scanner: ForegroundScanner):
        super().__init__(flags=QtCore.Qt.WindowType.FramelessWindowHint |
                               QtCore.Qt.WindowType.WindowStaysOnTopHint |
                               QtCore.Qt.WindowType.Tool)
        self.scanner = scanner
        self.elements: List[UIElement] = []
        self.badges:   List[Badge] = []
        self.input: str = ""
        self.input_timer = QtCore.QTimer(singleShot=True, timeout=self.process_input)
        self.refresh_timer = QtCore.QTimer(interval=500, timeout=self.refresh)  # 0.5 s

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.installEventFilter(self)
        self.refresh()
        self.refresh_timer.start()
        self.show()

    # ---------------- rendering ----------------
    def refresh(self):
        elems, win_rect = self.scanner.scan()
        # If nothing changed, skip heavy rebuild
        if [e.ctrl for e in elems] == [e.ctrl for e in self.elements]:
            return

        # Re-lay out overlay to match window bounds
        self.setGeometry(win_rect)
        self.move(win_rect.x(), win_rect.y())

        for b in self.badges:
            b.deleteLater()
        self.badges.clear()
        self.elements = elems
        for e in self.elements:
            b = Badge(e, self)
            b.show()
            self.badges.append(b)
        # Debug
        print(f"🔄 {len(self.elements)} controls numbered on '{self.scanner.last_title}'.")

    # ---------------- input --------------------
    def eventFilter(self, _, ev):
        if ev.type() == QtCore.QEvent.Type.KeyPress:
            k = ev.key()
            if k == QtCore.Qt.Key.Key_Escape:
                self.close(); return True
            if QtCore.Qt.Key.Key_0 <= k <= QtCore.Qt.Key.Key_9:
                self.input += str(k - QtCore.Qt.Key.Key_0)
                self.input_timer.start(700)  # wait for more digits
                return True
        return super().eventFilter(_, ev)

    def process_input(self):
        if not self.input:
            return
        num = int(self.input)
        self.input = ""
        tgt = next((e for e in self.elements if e.number == num), None)
        if not tgt:
            print(f"❓ No element #{num}")
            return
        print(f"🎯 Clicking {num} ({tgt.role})")
        self.invoke(tgt)
        QtCore.QTimer.singleShot(1000, self.refresh)  # refresh after UI settles

    # ---------------- action -------------------
    @staticmethod
    def invoke(elem: UIElement):
        try:
            elem.ctrl.SetFocus()
            if elem.ctrl.InvokePatternAvailable:
                elem.ctrl.InvokePattern.Invoke(); return
        except Exception as e:
            print(f"⚠ InvokePattern failed: {e}")
        # Fallback: centre click
        br = elem.ctrl.BoundingRectangle
        auto.MouseClick(int((br.left + br.right) / 2), int((br.top + br.bottom) / 2))

###############################################################################
# Main                                                                         #
###############################################################################
def main():
    print("Foreground‑window overlay – numbers update with each Alt‑Tab (Esc quits)\n")
    # Prevent Qt from showing the native Windows help button (older PyQt6 builds
        # may not have this enum value – guard with `hasattr`).
    try:
        QtCore.QCoreApplication.setAttribute(
        QtCore.Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton
            )
    except AttributeError:
        pass  # Running on a PyQt6 build < 6.5 – ignore
    app = QtWidgets.QApplication(sys.argv)
    overlay = Overlay(ForegroundScanner())
    sys.exit(app.exec())

if __name__ == "__main__":
    try:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("⚠  Run as Administrator for full UI control.")
    except Exception:
        pass
    main()
