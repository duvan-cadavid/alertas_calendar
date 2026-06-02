import math
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer, QThread, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QApplication

# ── Windows: IAudioMeterInformation peak reader ───────────────────────────────
if sys.platform == 'win32':
    import ctypes
    import uuid as _uuid_mod

    class _GUID(ctypes.Structure):
        _fields_ = [
            ('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
            ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_uint8 * 8),
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
        """IAudioMeterInformation — reads default capture device peak (0.0–1.0)."""
        _CLSCTX = 23
        _eCapture = 1
        _eConsole = 0

        def __init__(self):
            self._meter = 0
            self._sz    = ctypes.sizeof(ctypes.c_void_p)
            try:
                self._open()
            except Exception:
                pass

        def _fn(self, obj: int, slot: int, *argtypes):
            vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p)).contents.value
            addr = ctypes.cast(
                ctypes.c_void_p(vtbl + slot * self._sz),
                ctypes.POINTER(ctypes.c_void_p),
            ).contents.value
            return ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(addr)

        def _release(self, obj: int):
            self._fn(obj, 2)(obj)

        def _open(self):
            ole32 = ctypes.windll.ole32
            CLSID = _make_guid('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
            IID_E = _make_guid('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
            IID_M = _make_guid('{C02216F6-8C67-4B5B-9D00-D008E73E0064}')

            enum = ctypes.c_void_p()
            if ole32.CoCreateInstance(
                ctypes.byref(CLSID), None, self._CLSCTX,
                ctypes.byref(IID_E), ctypes.byref(enum),
            ) < 0 or not enum.value:
                return

            dev = ctypes.c_void_p()
            hr = self._fn(enum.value, 4,
                          ctypes.c_int, ctypes.c_int,
                          ctypes.POINTER(ctypes.c_void_p))(
                enum.value, self._eCapture, self._eConsole, ctypes.byref(dev))
            self._release(enum.value)
            if hr < 0 or not dev.value:
                return

            meter = ctypes.c_void_p()
            hr = self._fn(dev.value, 3,
                          ctypes.POINTER(_GUID), ctypes.c_uint,
                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                dev.value, ctypes.byref(IID_M), self._CLSCTX,
                None, ctypes.byref(meter))
            self._release(dev.value)
            if hr >= 0 and meter.value:
                self._meter = meter.value

        def peak(self) -> float:
            """Return 0.0–1.0, or -1.0 when unavailable (triggers fallback animation)."""
            if not self._meter:
                return -1.0
            try:
                val = ctypes.c_float()
                hr  = self._fn(self._meter, 3, ctypes.POINTER(ctypes.c_float))(
                    self._meter, ctypes.byref(val))
                return max(0.0, min(1.0, val.value)) if hr >= 0 else -1.0
            except Exception:
                return -1.0

        def close(self):
            if self._meter:
                self._release(self._meter)
                self._meter = 0


# ── Linux: parec-based microphone level reader ────────────────────────────────
class _LinuxMicReader(QThread):
    """Reads raw audio from PulseAudio/PipeWire default source via parec.

    Emits level_ready(float) with RMS amplitude 0.0–1.0 every ~100 ms.
    Falls back gracefully if parec is not installed.
    """
    level_ready = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None

    def run(self):
        import select
        try:
            self._proc = subprocess.Popen(
                ['parec', '--device=@DEFAULT_SOURCE@',
                 '--channels=1', '--rate=8000', '--format=u8'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            chunk = 800   # 100 ms at 8 kHz mono u8
            while not self.isInterruptionRequested():
                ready, _, _ = select.select([self._proc.stdout], [], [], 0.15)
                if not ready:
                    continue
                data = self._proc.stdout.read(chunk)
                if not data:
                    break
                # u8 center = 128; signed amplitude → RMS / 128 → 0.0-1.0
                rms = math.sqrt(
                    sum((b - 128) ** 2 for b in data) / len(data)
                ) / 128.0
                self.level_ready.emit(min(1.0, rms))
        except Exception:
            pass
        finally:
            if self._proc:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=1)
                except Exception:
                    pass

    def stop(self):
        self.requestInterruption()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self.quit()
        self.wait(1500)


# ── VU bar ────────────────────────────────────────────────────────────────────
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


def _to_display(peak: float) -> float:
    """Map linear amplitude 0–1 to display level 0–1 on a dB scale.

    Range: –50 dB (silence) → 0 %,  0 dB (full scale) → 100 %.
    This gives natural visual sensitivity: quiet speech sits in the
    green zone instead of barely moving a linear bar.
    """
    db = 20.0 * math.log10(max(peak, 1e-6))
    return max(0.0, min(1.0, (db + 50.0) / 50.0))


# Color-zone thresholds (on the 0–1 display scale after log mapping):
#  < 0.35  → gray   — too quiet for clear speech  (< –32 dBFS)
#  0.35–0.80 → green  — good level for human ear   (–32 to –10 dBFS)
#  0.80–0.93 → yellow — getting loud               (–10 to –3.5 dBFS)
#  ≥ 0.93  → red    — shouting / clipping risk    (> –3.5 dBFS)
_GRAY   = QColor('#585b70')
_GREEN  = QColor('#a6e3a1')
_YELLOW = QColor('#f9e2af')
_RED    = QColor('#f38ba8')


class _VuBar(QWidget):
    """Microphone level bar with dB-scale display and four-zone color coding."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_BAR_W, _BAR_HEIGHT + 4)
        self._display = 0.0   # display level 0–1 after log mapping
        self._anim_t  = 0     # tick counter for fallback animation only

    def set_level(self, peak: float):
        """peak: raw linear 0.0–1.0, or < 0 to advance the fallback animation."""
        if peak < 0.0:
            # No real meter available — sine-wave animation fallback
            self._anim_t += 1
            base   = 0.45 + 0.35 * abs(math.sin(self._anim_t * 0.18))
            ripple = 0.15 * abs(math.sin(self._anim_t * 0.73))
            peak   = min(1.0, base + ripple)

        new_d = _to_display(peak)
        # Instant rise, exponential decay (×0.72 per ~100 ms tick)
        self._display = max(new_d, self._display * 0.72)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background track
        p.setBrush(QBrush(QColor('#1e1e2e')))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 2, _BAR_W, _BAR_HEIGHT, 4, 4)

        fill = int(_BAR_W * self._display)
        if fill <= 0:
            return

        lv = self._display
        if lv < 0.35:
            color = _GRAY
        elif lv < 0.80:
            color = _GREEN
        elif lv < 0.93:
            color = _YELLOW
        else:
            color = _RED

        p.setBrush(QBrush(color))
        p.drawRoundedRect(0, 2, fill, _BAR_HEIGHT, 4, 4)


# ── RecordingIndicator ────────────────────────────────────────────────────────
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

        self._elapsed          = 0
        self._paused           = False
        self._drag_pos         = QPoint()
        self._linux_dry_ticks  = 0   # ticks since last level_ready on Linux

        self._build_ui()
        self._position_bottom_right()
        self._start_meter()

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick)
        self._clock.start(100)    # 10 fps

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

    def _position_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        margin_x = int(screen.width()  * 0.02)
        margin_y = int(screen.height() * 0.10)
        x = screen.right()  - self.width()  - margin_x
        y = screen.bottom() - self.height() - margin_y
        self.move(x, y)

    # ── Drag to move ──────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    # ── Meter setup ───────────────────────────────────────────────

    def _start_meter(self):
        self._win_meter    = None
        self._linux_reader = None

        if sys.platform == 'win32':
            self._win_meter = _WindowsMicMeter()
        else:
            reader = _LinuxMicReader(self)
            reader.level_ready.connect(self._on_linux_level)
            reader.start()
            self._linux_reader = reader

    # ── Slots ─────────────────────────────────────────────────────

    def _on_linux_level(self, level: float):
        """Receive real audio level from parec reader and reset dry-tick counter."""
        self._linux_dry_ticks = 0
        self._vu.set_level(level)

    def _tick(self):
        if self._win_meter:
            self._vu.set_level(self._win_meter.peak())
        elif self._linux_reader:
            # If parec hasn't delivered data for >3 ticks (300 ms) — it either
            # isn't installed or the device failed — fall back to animation so
            # the bar shows something instead of staying invisible at level 0.
            self._linux_dry_ticks += 1
            if self._linux_dry_ticks > 3:
                self._vu.set_level(-1.0)
        else:
            self._vu.set_level(-1.0)

        # Clock update (every 10 ticks = 1 s)
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

    # ── Cleanup ───────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._win_meter:
            self._win_meter.close()
            self._win_meter = None
        if self._linux_reader:
            self._linux_reader.stop()
            self._linux_reader = None
        super().closeEvent(event)
