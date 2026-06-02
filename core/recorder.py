import os
import sys
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication


class ScreenInfo:
    def __init__(self, index: int, name: str,
                 x: int, y: int, width: int, height: int, scale: float = 1.0):
        self.index = index
        self.name = name
        self.x = x           # physical pixels
        self.y = y           # physical pixels
        self.width = width   # physical pixels
        self.height = height # physical pixels
        self.scale = scale

    def label(self) -> str:
        scale_str = f'  ·  {self.scale:.0%} DPI' if self.scale != 1.0 else ''
        return f"Pantalla {self.index + 1} — {self.name}  ({self.width}×{self.height}{scale_str})"


def get_screens() -> List[ScreenInfo]:
    """Return screens with physical pixel dimensions and correct capture positions.

    Uses platform-native APIs so coordinates are correct for any multi-monitor
    setup regardless of DPI mix, resolution, or number of screens:
      - Linux X11:  xrandr --query  (matched by connector name, then by size)
      - Windows:    EnumDisplayMonitors via ctypes  (matched by physical size)
      - Fallback:   Qt geometry × devicePixelRatio (works for same-DPI setups)
    """
    qt_screens = QApplication.screens()
    if sys.platform == 'win32':
        phys_map = _win32_monitor_positions(qt_screens)
    else:
        phys_map = _xrandr_geometry(qt_screens)

    result = []
    for i, s in enumerate(qt_screens):
        g = s.geometry()
        ratio = s.devicePixelRatio()
        if i in phys_map:
            x, y, w, h = phys_map[i]
        else:
            # Fallback — works when all monitors share the same DPI ratio
            x = round(g.x() * ratio)
            y = round(g.y() * ratio)
            w = round(g.width() * ratio)
            h = round(g.height() * ratio)
        result.append(ScreenInfo(i, s.name() or f"Monitor {i + 1}", x, y, w, h, ratio))
    return result


def _xrandr_geometry(qt_screens: list) -> dict:
    """Map Qt screen index → (x, y, w, h) in X11 physical pixels via xrandr.

    Matching strategy (in order):
      1. Connector name — QScreen.name() matches the xrandr output name
         (DP-0, HDMI-1, eDP-1…).  Works even with identical resolutions.
      2. Physical resolution — fallback for systems where Qt names differ.
         Uses a 'used positions' set to avoid assigning the same monitor twice.
    """
    import re
    out: dict = {}
    try:
        r = subprocess.run(['xrandr', '--query'], capture_output=True, text=True, timeout=5)

        # connector_name → (x, y, w, h)
        by_name: dict = {}
        # (w, h) → list of (x, y, w, h)  — for the fallback
        by_size: dict = {}
        for m in re.finditer(
            r'^(\S+) connected(?: primary)? (\d+)x(\d+)\+(\d+)\+(\d+)',
            r.stdout, re.MULTILINE,
        ):
            name = m.group(1)
            w, h, x, y = int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))
            by_name[name] = (x, y, w, h)
            by_size.setdefault((w, h), []).append((x, y, w, h))

        used_xy: set = set()
        for i, s in enumerate(qt_screens):
            g = s.geometry()
            ratio = s.devicePixelRatio()
            pw = round(g.width() * ratio)
            ph = round(g.height() * ratio)

            # Strategy 1: name match
            if s.name() in by_name:
                entry = by_name[s.name()]
                out[i] = entry
                used_xy.add(entry[:2])
                continue

            # Strategy 2: size match (skip already-assigned positions)
            for entry in by_size.get((pw, ph), []):
                if entry[:2] not in used_xy:
                    out[i] = entry
                    used_xy.add(entry[:2])
                    break

    except Exception:
        pass
    return out


def _win32_monitor_positions(qt_screens: list) -> dict:
    """Map Qt screen index → (x, y, w, h) in physical pixels via Win32.

    EnumDisplayMonitors returns MONITORINFO.rcMonitor in physical virtual-desktop
    coordinates — the same system gdigrab uses — regardless of per-monitor DPI.
    Matching is done by physical resolution (w × h), tracking already-used
    entries so identical monitors are assigned to different Qt screens.
    """
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize',    wintypes.DWORD),
            ('rcMonitor', wintypes.RECT),
            ('rcWork',    wintypes.RECT),
            ('dwFlags',   wintypes.DWORD),
        ]

    monitors: list = []

    def _cb(hMon, _hDC, _lpRect, _lParam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hMon, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_void_p,
    )
    cb = MonitorEnumProc(_cb)   # keep alive until EnumDisplayMonitors returns
    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, None)
    except Exception:
        return {}

    out: dict = {}
    used: set = set()
    for i, s in enumerate(qt_screens):
        g = s.geometry()
        ratio = s.devicePixelRatio()
        pw = round(g.width() * ratio)
        ph = round(g.height() * ratio)
        for j, (x, y, w, h) in enumerate(monitors):
            if j not in used and w == pw and h == ph:
                out[i] = (x, y, w, h)
                used.add(j)
                break
    return out


def ffmpeg_available() -> bool:
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


AudioDevice = Tuple[str, str]   # (ffmpeg_device_id, display_name)


def get_audio_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    """Returns (mic_list, system_audio_list) — each item is (device_id, display_name)."""
    if sys.platform == 'win32':
        return _dshow_devices()
    return _pulse_devices()


def _dshow_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    """Enumerate DirectShow audio devices on Windows via FFmpeg."""
    import re
    mics: List[AudioDevice] = []
    sys_devs: List[AudioDevice] = []
    try:
        r = subprocess.run(
            ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
            capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace',
        )
        in_audio = False
        for line in r.stderr.splitlines():
            low = line.lower()
            # FFmpeg prints section headers like: "DirectShow audio devices"
            if 'directshow audio' in low:
                in_audio = True
                continue
            if 'directshow video' in low:
                in_audio = False
                continue
            if not in_audio:
                continue
            # Skip "Alternative name" lines (@device_cm_... / @device_pnp_...)
            if 'alternative name' in low:
                continue
            m = re.search(r'"([^"@][^"]*)"', line)
            if not m:
                continue
            name = m.group(1).strip()
            if not name:
                continue
            keywords = ('mix', 'stereo', 'loopback', 'what u hear', 'wave out')
            if any(k in name.lower() for k in keywords):
                sys_devs.append((name, name))
            else:
                mics.append((name, name))
    except Exception:
        pass
    return mics, sys_devs


def _pulse_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    """Enumerate PulseAudio/PipeWire sources on Linux with friendly names."""
    mics: List[AudioDevice] = []
    sys_devs: List[AudioDevice] = []
    try:
        r = subprocess.run(
            ['pactl', 'list', 'sources'],
            capture_output=True, text=True, timeout=8,
        )
        dev_name: Optional[str] = None
        dev_desc: Optional[str] = None
        dev_state: Optional[str] = None

        for line in r.stdout.splitlines():
            s = line.strip()
            if s.startswith('Name:'):
                dev_name = s.split(':', 1)[1].strip()
            elif s.startswith('Description:'):
                dev_desc = s.split(':', 1)[1].strip()
            elif s.startswith('State:'):
                dev_state = s.split(':', 1)[1].strip()

            # Each source block ends when we have all three fields
            if dev_name and dev_desc and dev_state is not None:
                # Skip null/virtual sinks and suspended devices
                skip_keywords = ('auto_null', 'null-sink', 'dummy')
                if (dev_state != 'SUSPENDED'
                        and not any(k in dev_name.lower() for k in skip_keywords)):
                    label = dev_desc  # human-readable
                    if 'monitor' in dev_name.lower():
                        sys_devs.append((dev_name, f"🔊 {label}"))
                    else:
                        mics.append((dev_name, f"🎙 {label}"))
                dev_name = dev_desc = dev_state = None

    except Exception:
        pass

    # Fallback: if pactl failed or found nothing, offer system default
    if not mics:
        mics.append(('default', '🎙 Micrófono predeterminado del sistema'))
    if not sys_devs:
        sys_devs.append(('default.monitor', '🔊 Audio del sistema (monitor predeterminado)'))

    return mics, sys_devs


# ── FFmpeg stderr parser ──────────────────────────────────────────────────────

_VERSION_PREFIXES = (
    'ffmpeg version', 'built with', 'configuration:', 'copyright',
    'libav', 'libsw', 'libpost', 'lib',
)

def _ffmpeg_error(stderr: str) -> str:
    """Return only the meaningful error lines from FFmpeg stderr output."""
    all_lines = [l.strip() for l in stderr.splitlines() if l.strip()]
    # Keep lines that are NOT version/library info
    error_lines = [
        l for l in all_lines
        if not any(l.lower().startswith(p) for p in _VERSION_PREFIXES)
    ]
    # If nothing survived filtering, fall back to all lines
    if not error_lines:
        error_lines = all_lines
    return '\n'.join(error_lines) if error_lines else 'Sin detalles de FFmpeg.'


# ── Segment thread ────────────────────────────────────────────────────────────

class _SegmentThread(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, cmd: List[str], output: str, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._output = output
        self._proc: Optional[subprocess.Popen] = None
        self._stopping = False

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,   # capturar para diagnóstico
            )
            _, stderr_bytes = self._proc.communicate()
            rc = self._proc.returncode

            # Código 255 es la salida normal cuando FFmpeg recibe 'q'
            normal_exit = rc in (0, 255) or self._stopping
            file_ok = os.path.exists(self._output) and os.path.getsize(self._output) > 0

            if file_ok and normal_exit:
                self.done.emit(self._output)
            elif not file_ok:
                msg = stderr_bytes.decode(errors='replace').strip()
                self.error.emit('FFmpeg no pudo iniciar la grabación:\n\n'
                                + _ffmpeg_error(msg))
        except FileNotFoundError:
            self.error.emit(
                'FFmpeg no está instalado o no está en el PATH.\n'
                'Descárgalo desde https://ffmpeg.org/download.html'
            )
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._stopping = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(b'q')
                self._proc.stdin.flush()
                self._proc.wait(timeout=10)
            except Exception:
                self._proc.kill()
                self._proc.wait()


# ── Concat thread ─────────────────────────────────────────────────────────────

class _ConcatThread(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, segments: List[str], output: str,
                 tmp: tempfile.TemporaryDirectory, parent=None):
        super().__init__(parent)
        self._segments = segments
        self._output = output
        self._tmp = tmp

    def run(self):
        try:
            if len(self._segments) == 1:
                shutil.copy2(self._segments[0], self._output)
            else:
                list_path = os.path.join(self._tmp.name, 'list.txt')
                with open(list_path, 'w', encoding='utf-8') as f:
                    for seg in self._segments:
                        f.write(f"file '{seg}'\n")
                cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                       '-i', list_path, '-c', 'copy', self._output]
                r = subprocess.run(cmd, capture_output=True, timeout=600)
                if r.returncode != 0:
                    raise RuntimeError(r.stderr.decode(errors='replace')[-300:])
            self.done.emit(self._output)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            try:
                self._tmp.cleanup()
            except Exception:
                pass


# ── ScreenRecorder ────────────────────────────────────────────────────────────

class ScreenRecorder(QObject):
    recording_started = pyqtSignal()
    paused = pyqtSignal()
    resumed = pyqtSignal()
    finished = pyqtSignal(str)   # final mp4 path
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[str] = []
        self._seg_thread: Optional[_SegmentThread] = None
        self._concat_thread: Optional[_ConcatThread] = None
        self._screen: Optional[ScreenInfo] = None
        self._mic: Optional[str] = None
        self._sys: Optional[str] = None
        self._out: str = ''
        self._tmp: Optional[tempfile.TemporaryDirectory] = None
        self._seg_idx = 0
        self._state = 'idle'   # idle | recording | pausing | paused | stopping

    @property
    def state(self) -> str:
        return self._state

    # ── Public API ────────────────────────────────────────────────

    def start(self, screen: ScreenInfo, output: str,
              mic: Optional[str] = None, sys_audio: Optional[str] = None):
        if self._state != 'idle':
            return
        self._screen = screen
        self._out = output
        self._mic = mic
        self._sys = sys_audio
        self._tmp = tempfile.TemporaryDirectory()
        self._segments = []
        self._seg_idx = 0
        self._state = 'recording'
        self._launch_segment()
        self.recording_started.emit()

    def pause(self):
        if self._state != 'recording':
            return
        self._state = 'pausing'
        if self._seg_thread:
            self._seg_thread.stop()

    def resume(self):
        if self._state != 'paused':
            return
        self._state = 'recording'
        self._launch_segment()
        self.resumed.emit()

    def stop(self):
        if self._state == 'idle':
            return
        if self._state in ('recording', 'pausing'):
            self._state = 'stopping'
            if self._seg_thread and self._seg_thread.isRunning():
                self._seg_thread.stop()
            else:
                self._finish()
        elif self._state == 'paused':
            self._state = 'stopping'
            self._finish()

    # ── Internal ──────────────────────────────────────────────────

    def _launch_segment(self):
        self._seg_idx += 1
        path = os.path.join(self._tmp.name, f'seg_{self._seg_idx:04d}.mp4')
        self._seg_thread = _SegmentThread(self._build_cmd(path), path, self)
        self._seg_thread.done.connect(self._on_segment_done)
        self._seg_thread.error.connect(self.error)
        self._seg_thread.start()

    def _on_segment_done(self, path: str):
        self._segments.append(path)
        s = self._state
        if s == 'pausing':
            self._state = 'paused'
            self.paused.emit()
        elif s == 'stopping':
            self._finish()

    def _finish(self):
        if not self._segments:
            self.error.emit('No se grabó ningún segmento.')
            self._state = 'idle'
            return
        tmp = self._tmp
        self._tmp = None
        self._concat_thread = _ConcatThread(self._segments, self._out, tmp, self)
        self._concat_thread.done.connect(self._on_concat_done)
        self._concat_thread.error.connect(self._on_concat_error)
        self._concat_thread.start()

    def _on_concat_done(self, path: str):
        self._state = 'idle'
        self.finished.emit(path)

    def _on_concat_error(self, msg: str):
        self._state = 'idle'
        self.error.emit(msg)

    def _build_cmd(self, output: str) -> List[str]:
        s = self._screen
        cmd = ['ffmpeg', '-y']

        if sys.platform == 'win32':
            cmd += [
                '-f', 'gdigrab',
                '-offset_x', str(s.x), '-offset_y', str(s.y),
                '-video_size', f'{s.width}x{s.height}',
                '-framerate', '30', '-i', 'desktop',
            ]
        else:
            disp = os.environ.get('DISPLAY', ':0.0')
            cmd += [
                '-f', 'x11grab',
                '-video_size', f'{s.width}x{s.height}',
                '-framerate', '30',
                '-i', f'{disp}+{s.x},{s.y}',
            ]

        audio_n = 0
        if self._mic:
            if sys.platform == 'win32':
                cmd += ['-f', 'dshow', '-i', f'audio={self._mic}']
            else:
                cmd += ['-f', 'pulse', '-i', self._mic]
            audio_n += 1
        if self._sys:
            if sys.platform == 'win32':
                cmd += ['-f', 'dshow', '-i', f'audio={self._sys}']
            else:
                cmd += ['-f', 'pulse', '-i', self._sys]
            audio_n += 1

        cmd += ['-vf', 'scale=1280:720', '-c:v', 'libx264', '-crf', '28', '-preset', 'fast']

        if audio_n == 2:
            cmd += [
                '-filter_complex', '[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=2[aout]',
                '-map', '0:v', '-map', '[aout]',
                '-c:a', 'aac', '-b:a', '128k',
            ]
        elif audio_n == 1:
            cmd += ['-c:a', 'aac', '-b:a', '128k']
        else:
            cmd += ['-an']

        cmd.append(output)
        return cmd
