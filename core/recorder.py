import logging
import os
import sys
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

# ── Recorder logger ────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / '.alertas_calendario' / 'recorder.log'

def _setup_logger() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('recorder')
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(fh)
    return logger

_log = _setup_logger()


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


def _get_ffmpeg_exe() -> str:
    """Return the ffmpeg executable, preferring the bundled copy on Windows.

    The Windows installer places ffmpeg.exe in {app}\\bin\\ and adds that
    directory to the system PATH — but the PATH update doesn't propagate to
    the installer's own child processes (the app itself when launched by the
    installer).  Checking the bundled path first avoids that race.
    """
    if sys.platform == 'win32':
        bundled = os.path.join(os.path.dirname(sys.executable), 'bin', 'ffmpeg.exe')
        if os.path.isfile(bundled):
            return bundled
    return 'ffmpeg'


def ffmpeg_available() -> bool:
    try:
        subprocess.run([_get_ffmpeg_exe(), '-version'], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


AudioDevice = Tuple[str, str]   # (ffmpeg_device_id, display_name)


def get_audio_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    """Returns (mic_list, system_audio_list) — each item is (device_id, display_name)."""
    if sys.platform == 'win32':
        return _windows_devices()
    return _pulse_devices()


def _windows_devices() -> Tuple[List[AudioDevice], List[AudioDevice]]:
    """Enumerate audio devices on Windows via DirectShow.

    Uses dshow because the bundled FFmpeg essentials build does not include
    WASAPI support.  Handles both FFmpeg ≤7 format (section headers) and the
    FFmpeg 8.x format where devices appear as `"Name" (audio)` on one line.
    """
    import re
    mics: List[AudioDevice] = []
    sys_devs: List[AudioDevice] = []

    ffmpeg = _get_ffmpeg_exe()
    _log.info('=== _windows_devices() start ===')
    _log.info('ffmpeg exe: %s', ffmpeg)

    keywords = ('mix', 'stereo', 'loopback', 'what u hear', 'wave out')

    def _classify(name: str):
        if any(k in name.lower() for k in keywords):
            _log.info('dshow sys audio: %r', name)
            sys_devs.append((name, f'🔊 {name}'))
        else:
            _log.info('dshow mic: %r', name)
            mics.append((name, f'🎙 {name}'))

    try:
        dshow_cmd = [ffmpeg, '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy']
        _log.info('dshow cmd: %s', dshow_cmd)
        r = subprocess.run(
            dshow_cmd,
            capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace',
        )
        _log.info('dshow returncode: %d', r.returncode)
        _log.info('dshow stderr:\n%s', r.stderr)

        # FFmpeg 8.x: `[...] "Name" (audio)` or `[...] "Name" (video)` on one line.
        # FFmpeg ≤7: section header `DirectShow audio devices`, then `  "Name"` lines.
        in_audio_section = False
        for line in r.stderr.splitlines():
            low = line.lower()
            if 'alternative name' in low:
                continue

            # FFmpeg 8.x — explicit (audio) / (video) tag on the same line
            m8 = re.search(r'"([^"]+)"\s+\(audio\)', line)
            if m8:
                name = m8.group(1).strip()
                if name and not name.startswith('@'):
                    _classify(name)
                continue
            if re.search(r'"[^"]+"\s+\(video\)', line):
                continue  # skip video devices

            # FFmpeg ≤7 — section headers
            if 'directshow audio' in low:
                in_audio_section = True
                continue
            if 'directshow video' in low:
                in_audio_section = False
                continue

            # FFmpeg ≤7 — device line inside audio section
            if in_audio_section:
                m7 = re.search(r'"([^"@][^"]*)"', line)
                if m7:
                    name = m7.group(1).strip()
                    if name:
                        _classify(name)

    except Exception as exc:
        _log.exception('dshow enumeration failed: %s', exc)

    _log.info('dshow result — mics: %d, sys: %d', len(mics), len(sys_devs))
    _log.info('=== _windows_devices() end ===')
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
            kwargs = {}
            if sys.platform == 'win32':
                # Prevent FFmpeg from opening a visible console window
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            self._proc = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                **kwargs,
            )

            # Read stderr in a background thread to prevent pipe-buffer
            # deadlock — keeping stdin OPEN so stop() can send 'q' later.
            # communicate() would close stdin immediately, making 'q' impossible.
            buf: List[bytes] = []
            def _read_stderr():
                try:
                    for chunk in iter(lambda: self._proc.stderr.read(4096), b''):
                        buf.append(chunk)
                except Exception:
                    pass
            reader = threading.Thread(target=_read_stderr, daemon=True)
            reader.start()

            self._proc.wait()           # blocks until FFmpeg exits
            reader.join(timeout=3)
            stderr_bytes = b''.join(buf)
            rc = self._proc.returncode
            stderr_text = stderr_bytes.decode(errors='replace').strip()

            _log.info('FFmpeg segment finished — rc=%d stopping=%s file_ok=%s',
                      rc, self._stopping,
                      os.path.exists(self._output) and os.path.getsize(self._output) > 0)
            _log.info('FFmpeg stderr:\n%s', stderr_text)

            # 0 = natural end, 255 = received 'q', negative = killed
            normal_exit = rc in (0, 255) or self._stopping
            file_ok = os.path.exists(self._output) and os.path.getsize(self._output) > 0

            if file_ok and normal_exit:
                self.done.emit(self._output)
            elif not file_ok:
                self.error.emit('FFmpeg no pudo iniciar la grabación:\n\n'
                                + _ffmpeg_error(stderr_text))
        except FileNotFoundError:
            _log.error('ffmpeg not found: %s', self._cmd[0])
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
                # Send 'q' — FFmpeg stops gracefully and writes the moov atom
                self._proc.stdin.write(b'q')
                self._proc.stdin.flush()
                self._proc.stdin.close()
                # Allow up to 30 s to finalize the file (large moov atoms)
                self._proc.wait(timeout=30)
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
                # Re-mux with faststart so the moov atom is at the front.
                # shutil.copy2 would preserve a potentially unplayable file.
                cmd = [
                    _get_ffmpeg_exe(), '-y', '-i', self._segments[0],
                    '-c', 'copy', '-movflags', '+faststart',
                    self._output,
                ]
            else:
                list_path = os.path.join(self._tmp.name, 'list.txt')
                with open(list_path, 'w', encoding='utf-8') as f:
                    for seg in self._segments:
                        f.write(f"file '{seg}'\n")
                cmd = [
                    _get_ffmpeg_exe(), '-y',
                    '-f', 'concat', '-safe', '0', '-i', list_path,
                    '-c', 'copy', '-movflags', '+faststart',
                    self._output,
                ]
            extra = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
            r = subprocess.run(cmd, capture_output=True, timeout=600, **extra)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode(errors='replace')[-400:])
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
        cmd = [_get_ffmpeg_exe(), '-y']

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
                # dshow — bundled FFmpeg essentials does not include WASAPI
                cmd += ['-f', 'dshow', '-i', f'audio={self._mic}']
            else:
                cmd += ['-f', 'pulse', '-i', self._mic]
            audio_n += 1
        if self._sys:
            if sys.platform == 'win32':
                # dshow — Stereo Mix or similar loopback device from dshow enumeration
                cmd += ['-f', 'dshow', '-i', f'audio={self._sys}']
            else:
                cmd += ['-f', 'pulse', '-i', self._sys]
            audio_n += 1

        # yuv420p  → required by WhatsApp, Android, iOS and all hardware decoders.
        #            Screen capture defaults to yuv444p which Chrome plays but
        #            mobile devices show as black video.
        # baseline → H.264 Baseline profile: widest device compatibility.
        # level 4.0 → supports up to 1080p30; accepted by all WhatsApp clients.
        # scale with force_original_aspect_ratio + pad ensures even dimensions
        # (H.264 requires width and height divisible by 2).
        cmd += [
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,'
                   'pad=1280:720:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libx264',
            '-profile:v', 'baseline',
            '-level:v', '4.0',
            '-pix_fmt', 'yuv420p',
            '-crf', '28',
            '-preset', 'fast',
        ]

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
        _log.info('=== _build_cmd ===')
        _log.info('mic=%r  sys_audio=%r', self._mic, self._sys)
        _log.info('cmd: %s', ' '.join(cmd))
        return cmd
