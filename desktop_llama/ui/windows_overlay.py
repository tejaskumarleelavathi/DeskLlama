#!/usr/bin/env python3
""" Universal numbered overlay for Windows desktop (safe version). """
from __future__ import annotations

# -- env tweaks AFTER future-import ------------------------------------------
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from typing import List, Tuple
from dataclasses import dataclass
from PyQt6 import QtCore, QtGui, QtWidgets
try:
    import uiautomation as auto
except ImportError:
    print("✖  pip install uiautomation PyQt6"); sys.exit(1)

# ───────── helpers ───────────────────────────────────────────────────────────
def _exists(ctrl: auto.Control) -> bool:
    """True if the element is still alive (no LookupError)."""
    try:
        _ = ctrl.ControlType         # triggers a property fetch
        return True
    except LookupError:
        return False

# ───────── data model ────────────────────────────────────────────────────────
@dataclass
class UIElement:
    number: int
    ctrl:   auto.Control
    @property
    def rect(self) -> QtCore.QRectF:
        br = self.ctrl.BoundingRectangle
        return QtCore.QRectF(br.left, br.top, br.right-br.left, br.bottom-br.top)
    @property
    def centre(self) -> QtCore.QPoint:
        r = self.rect
        return QtCore.QPoint(int(r.x()+r.width()/2), int(r.y()+r.height()/2))

# ───────── scanners ──────────────────────────────────────────────────────────
BTN_TYPES = {"ButtonControl", "TabItemControl", "TitleBarControl"}

def _collect(node: auto.Control, bucket: list[auto.Control]):
    """Depth-first walk, forgiving stale children."""
    try:
        if ((node.ControlTypeName in BTN_TYPES or
             node.ControlTypeName.endswith("ButtonControl")) and
                node.BoundingRectangle):
            bucket.append(node)
        for ch in node.GetChildren():
            _collect(ch, bucket)
    except LookupError:
        return                                   # node went stale – skip

def scan_window() -> list[auto.Control]:
    fg = auto.GetForegroundControl()
    out: list[auto.Control] = []
    if fg: _collect(fg, out)
    return out

def scan_taskbar() -> list[auto.Control]:
    """Return task-bar buttons or [] if explorer isn’t ready."""
    try:
        tb = auto.WindowControl(ClassName="Shell_TrayWnd")
        if not _exists(tb):
            return []
        out: list[auto.Control] = []
        _collect(tb, out)
        return out
    except LookupError:
        return []                                # explorer not ready

def scan_all() -> Tuple[List[UIElement], QtCore.QRect]:
    ctrls = scan_window() + scan_taskbar()
    ctrls.sort(key=lambda c: (-c.BoundingRectangle.top, c.BoundingRectangle.left))
    elems = [UIElement(i+1, c) for i, c in enumerate(ctrls)]
    desktop = QtCore.QRect()
    for s in QtGui.QGuiApplication.screens():
        desktop = desktop.united(s.geometry())
    return elems, desktop

# ───────── badge + overlay (unchanged from previous answer) ──────────────────
BADGE_BG   = QtGui.QColor(0, 0, 0, 235)
BADGE_TXT  = QtGui.QColor("white")
LEADER_CLR = QtGui.QColor(170, 170, 170, 180)
BORDER_CLR = QtGui.QColor(255, 255, 255, 90)

class Badge(QtWidgets.QLabel):
    def __init__(self, elem: UIElement, pos: QtCore.QPoint,
                 overlay: QtWidgets.QWidget):
        super().__init__(str(elem.number), overlay)
        self.elem = elem
        self.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        fm = QtGui.QFontMetrics(self.font())
        pad = 4
        self.w, self.h = fm.horizontalAdvance(self.text())+pad*2, fm.height()+pad
        self.resize(self.w, self.h)
        self.move(pos)
    def paintEvent(self, _):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setBrush(BADGE_BG); p.setPen(QtGui.QPen(BORDER_CLR, .6))
        p.drawRoundedRect(self.rect(), 3, 3)
        p.setPen(BADGE_TXT)
        p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, self.text())
        p.setPen(QtGui.QPen(LEADER_CLR, 1.0))
        start = QtCore.QPoint(self.w//2, self.h//2)
        end   = self.parent().mapFromGlobal(self.elem.centre)
        p.drawLine(start, end)

class Overlay(QtWidgets.QWidget):
    def __init__(self):
        flags = (QtCore.Qt.WindowType.FramelessWindowHint|
                 QtCore.Qt.WindowType.WindowStaysOnTopHint|
                 QtCore.Qt.WindowType.Tool)
        super().__init__(flags=flags)
        self.elems: list[UIElement] = []; self.badges: list[Badge] = []; self.input=""
        self.inp_timer = QtCore.QTimer(singleShot=True, timeout=self._commit)
        self.ref_timer = QtCore.QTimer(interval=700, timeout=self.refresh)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.installEventFilter(self); self.refresh(); self.ref_timer.start(); self.show()
    @staticmethod
    def _place(x:int,y:int,w:int,h:int,occ:list[QtCore.QRect])->QtCore.QPoint:
        r=QtCore.QRect(x,y,w,h)
        while any(r.intersects(o) for o in occ): r.translate(0,h+2)
        occ.append(r); return r.topLeft()
    def refresh(self):
        elems, desk = scan_all()
        if [e.ctrl for e in elems]==[e.ctrl for e in self.elems]: return
        self.setGeometry(desk); self.move(desk.topLeft())
        for b in self.badges: b.deleteLater()
        self.badges.clear(); self.elems=elems
        occ: list[QtCore.QRect]=[]
        for e in elems:
            raw_x=int(e.rect.x()-desk.x()-6); raw_y=int(e.rect.y()-desk.y()-6)
            probe=Badge(e, QtCore.QPoint(0,0), self)
            pos=self._place(raw_x,raw_y,probe.w,probe.h,occ); probe.move(pos)
            self.badges.append(probe)
        for b in self.badges: b.show()
    def eventFilter(self,_,ev):
        if ev.type()==QtCore.QEvent.Type.KeyPress:
            k=ev.key(); qt=QtCore.Qt
            if k==qt.Key.Key_Escape: self.close(); return True
            if qt.Key.Key_0<=k<=qt.Key.Key_9:
                self.input+=str(k-qt.Key.Key_0); self.inp_timer.start(600); return True
            if k in (qt.Key.Key_Return,qt.Key.Key_Enter,qt.Key.Key_Space):
                self._commit(); return True
            if k==qt.Key.Key_Backspace: self.input=self.input[:-1]; return True
        return super().eventFilter(_,ev)
    def _commit(self):
        if not self.input: return
        num=int(self.input); self.input=""
        tgt=next((e for e in self.elems if e.number==num),None)
        if tgt: self._click(tgt)
    @staticmethod
    def _click(el:UIElement):
        try:
            el.ctrl.SetFocus()
            if el.ctrl.InvokePatternAvailable: el.ctrl.InvokePattern.Invoke(); return
        except Exception: pass
        br=el.ctrl.BoundingRectangle
        auto.MouseClick(int((br.left+br.right)/2), int((br.top+br.bottom)/2))

# ───────── main ─────────────────────────────────────────────────────────────
if __name__=="__main__":
    if hasattr(QtCore.Qt.ApplicationAttribute,"AA_DisableHighDpiScaling"):
        QtCore.QCoreApplication.setAttribute(
            QtCore.Qt.ApplicationAttribute.AA_DisableHighDpiScaling, True)
    app = QtWidgets.QApplication(sys.argv)
    _   = Overlay()
    sys.exit(app.exec())

