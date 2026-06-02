import math
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QApplication

# ── Windows Core Audio peak meter (no extra deps) ─────────────────────────────
if sys.platform == 'win32':
    import ctypes
    import uuid as _uuid_mod

    class _GUID(ctypes.Structure):
        _fields_ = [
            ('Data1', ctypes.c_uint32),
            ('Data2', ctypes.c_uint16),
            ('Data3', ctypes.c_uint16),
            ('Data4', ctypes.c_uint8 * 8),
        ]

    def _make_guid(s: str) -> '_GUID':
        u = _uuid_mod.UUID(s)
        b = u.bytes_le
        g = _GUID()
        g.Data1 = int.from_bytes(b[0:4], 'little')
        g.Data2 = int.from_bytes(b[4:6], 'little')
        g.Data3 = int.from_bytes(b[6:8], 'little')
        for i in range(8):
            g.Data4[i] = b[8 + i]
        return g

    class _WindowsMicMeter:
        """IAudioMeterInformation peak reader — zero extra dependencies.

        Reads the Windows default capture device peak (same value shown in
        the Sound settings microphone level indicator).  Qt initializes COM
        on the main thread before this is ever called, so no CoInitialize
        call is needed here.
        """
        _CLSCTX_ALL = 23
        _eCapture   = 1   # eDataFlow
        _eConsole   = 0   # eRole

        def __init__(self):
            self._meter: int = 0   # raw IAudioMeterInformation pointer
            self._sz = ctypes.sizeof(ctypes.c_void_p)
            try:
                self._open()
            except Exception:
                pass

        # ── vtable helpers ────────────────────────────────────────

        def _fn(self, obj: int, slot: int, *argtypes):
            """Return a callable for vtable method at `slot` on `obj`."""
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value
            addr = ctypes.cast(
                ctypes.c_void_p(vtbl + slot * self._sz),
                ctypes.POINTER(ctypes.c_void_p),
            ).contents.value
            return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(addr)

        def _release(self, obj: int):
            self._fn(obj, 2)(obj)   # IUnknown::Release

        # ── COM setup ─────────────────────────────────────────────

        def _open(self):
            ole32 = ctypes.windll.ole32

            CLSID = _make_guid('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
            IID_E = _make_guid('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
            IID_M = _make_guid('{C02216F6-8C67-4B5B-9D00-D008E73E0064}')

            # CoCreateInstance → IMMDeviceEnumerator
            enum = ctypes.c_void_p()
            hr = ole32.CoCreateInstance(
                ctypes.byref(CLSID), None, self._CLSCTX_ALL,
                ctypes.byref(IID_E), ctypes.byref(enum),
            )
            if hr < 0 or not enum.value:
                return

            # GetDefaultAudioEndpoint(eCapture, eConsole, &dev)  [vtable slot 4]
            dev = ctypes.c_void_p()
            hr = self._fn(enum.value, 4,
                          ctypes.c_int, ctypes.c_int,
                          ctypes.POINTER(ctypes.c_void_p))(
                enum.value, self._eCapture, self._eConsole, ctypes.byref(dev))
            self._release(enum.value)
            if hr < 0 or not dev.value:
                return

            # IMMDevice::Activate(IID_M, CLSCTX_ALL, NULL, &meter)  [vtable slot 3]
            meter = ctypes.c_void_p()
            hr = self._fn(dev.value, 3,
                          ctypes.POINTER(_GUID), ctypes.c_uint,
                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                dev.value, ctypes.byref(IID_M), self._CLSCTX_ALL,
                None, ctypes.byref(meter))
            self._release(dev.value)
            if hr < 0 or not meter.value:
                return

            self._meter = meter.value

        # ── Public API ────────────────────────────────────────────

        def peak(self) -> float:
            """Return 0.0–1.0, or -1.0 if unavailable (triggers fallback animation)."""
            if not self._meter:
                return -1.0
            try:
                val = ctypes.c_float()
                hr = self._fn(self._meter, 3,
                              ctypes.POINTER(ctypes.c_float))(
                    self._meter, ctypes.byref(val))
                return max(0.0, min(1.0, val.value)) if hr >= 0 else -1.0
            except Exception:
                return -1.0

        def close(self):
            if self._meter:
                self._release(self._meter)
                self._meter = 0


# ── Style ──────────────────────────────────────────────────────────────────────

_STYLE = """
QWidget#indicator {
    background-color: #11111b;
    border: 2px solid #f38ba8;
    border-radius: 12px;
}
QLabel#rec_dot  { color: #f38ba8; font-size: 13px; font-weight: bold; }
QLabel#rec_time { color: #cdd6f4; font-size: 13px; font-family: monospace; font-weight: bold; }
QPushButton#btn_stop {
    background-color: #f38ba8; color: #11111b;
    border: none; border-radius: 6px;
    font-size: 12px; font-weight: bold;
    padding: 4px 10px;
}
QPushButton#btn_stop:hover { background-color: #ff99b0; }
QPushButton#btn_pause {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    font-size: 12px; padding: 4px 10px;
}
QPushButton#btn_pause:hover { background-color: #45475a; }
"""

_BAR_HEIGHT = 8
_BAR_W      = 220


class _VuBar(QWidget):
    """Microphone level bar.  Accepts real peak values or falls back to animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_BAR_W, _BAR_HEIGHT + 4)
        self._level  = 0.0
        self._anim_t = 0   # tick counter used only for the fallback animation

    def set_level(self, level: float):
        """level: 0.0–1.0 (real peak) or -1.0 to advance the fallback animation."""
        if level < 0.0:
            # No meter available — keep the sine-wave animation
            self._anim_t += 1
            base   = 0.45 + 0.35 * abs(math.sin(self._anim_t * 0.18))
            ripple = 0.15 * abs(math.sin(self._anim_t * 0.73))
            level  = min(1.0, base + ripple)

        # Smooth: instant rise, exponential decay (0.75 per 100 ms tick)
        self._level = max(level, self._level * 0.75)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor('#313244')))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 2, _BAR_W, _BAR_HEIGHT, 4, 4)
        fill = int(_BAR_W * self._level)
        if fill > 0:
            ratio = self._level
            if ratio < 0.6:
                r, g = int(ratio / 0.6 * 180), 220
            else:
                r, g = 220, int((1 - (ratio - 0.6) / 0.4) * 220)
            p.setBrush(QBrush(QColor(r, g, 60)))
            p.drawRoundedRect(0, 2, fill, _BAR_HEIGHT, 4, 4)


class RecordingIndicator(QWidget):
    """Small always-on-top floating window shown during screen recording."""
    pause_clicked = pyqtSignal()
    stop_clicked  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('indicator')
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(_STYLE)
        self.setFixedSize(300, 76)

        self._elapsed = 0
        self._paused  = False
        self._meter   = _WindowsMicMeter() if sys.platform == 'win32' else None

        self._build_ui()
        self._position_top_right()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(100)   # 10 fps

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget(self)
        container.setObjectName('indicator')
        container.setGeometry(0, 0, 300, 76)

        root = QVBoxLayout(container)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._dot = QLabel('● GRABANDO')
        self._dot.setObjectName('rec_dot')
        row.addWidget(self._dot)

        row.addStretch()

        self._time_lbl = QLabel('00:00:00')
        self._time_lbl.setObjectName('rec_time')
        row.addWidget(self._time_lbl)

        self._btn_pause = QPushButton('⏸')
        self._btn_pause.setObjectName('btn_pause')
        self._btn_pause.setFixedWidth(32)
        self._btn_pause.clicked.connect(self._on_pause)
        row.addWidget(self._btn_pause)

        btn_stop = QPushButton('⏹')
        btn_stop.setObjectName('btn_stop')
        btn_stop.setFixedWidth(32)
        btn_stop.clicked.connect(self.stop_clicked)
        row.addWidget(btn_stop)

        root.addLayout(row)

        self._vu = _VuBar(self)
        root.addWidget(self._vu, alignment=Qt.AlignmentFlag.AlignLeft)

    def _position_top_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 16, screen.top() + 16)

    # ── Slots ─────────────────────────────────────────────────────

    def _tick(self):
        peak = self._meter.peak() if self._meter else -1.0
        self._vu.set_level(peak)

        if self._elapsed % 10 == 0 and not self._paused:
            secs = self._elapsed // 10
            h, r = divmod(secs, 3600)
            m, s = divmod(r, 60)
            self._time_lbl.setText(f'{h:02d}:{m:02d}:{s:02d}')
        if not self._paused:
            self._elapsed += 1

    def _on_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._dot.setText('⏸ PAUSADO')
            self._dot.setStyleSheet('color: #fb923c; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('▶')
        else:
            self._dot.setText('● GRABANDO')
            self._dot.setStyleSheet('color: #f38ba8; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('⏸')
        self.pause_clicked.emit()

    def set_paused(self, paused: bool):
        self._paused = paused
        if paused:
            self._dot.setText('⏸ PAUSADO')
            self._dot.setStyleSheet('color: #fb923c; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('▶')
        else:
            self._dot.setText('● GRABANDO')
            self._dot.setStyleSheet('color: #f38ba8; font-size: 13px; font-weight: bold;')
            self._btn_pause.setText('⏸')

    def closeEvent(self, event):
        if self._meter:
            self._meter.close()
            self._meter = None
        super().closeEvent(event)
