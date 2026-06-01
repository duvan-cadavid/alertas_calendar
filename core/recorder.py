import os
import sys
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication


class ScreenInfo:
    def __init__(self, index: int, name: str, x: int, y: int, width: int, height: int):
        self.index = index
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def label(self) -> str:
        return f"Pantalla {self.index + 1} — {self.name}  ({self.width}×{self.height})"


def get_screens() -> List[ScreenInfo]:
    result = []
    for i, s in enumerate(QApplication.screens()):
        g = s.geometry()
        result.append(ScreenInfo(i, s.name() or f"Monitor {i + 1}", g.x(), g.y(), g.width(), g.height()))
    return result


def ffmpeg_available() -> bool:
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def get_audio_devices() -> Tuple[List[str], List[str]]:
    """Returns (mic_list, system_audio_list)."""
    if sys.platform == 'win32':
        return _dshow_devices()
    return _pulse_devices()


def _dshow_devices() -> Tuple[List[str], List[str]]:
    mics: List[str] = []
    sys_devs: List[str] = []
    try:
        r = subprocess.run(
            ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
            capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace',
        )
        import re
        in_audio = False
        for line in r.stderr.splitlines():
            low = line.lower()
            if '"audio"' in low:
                in_audio = True
            elif '"video"' in low:
                in_audio = False
            if not in_audio:
                continue
            m = re.search(r'"([^"]+)"', line)
            if m:
                name = m.group(1)
                keywords = ('mix', 'stereo', 'loopback', 'what u hear', 'wave out', 'wasapi')
                if any(k in name.lower() for k in keywords):
                    sys_devs.append(name)
                else:
                    mics.append(name)
    except Exception:
        pass
    return mics, sys_devs


def _pulse_devices() -> Tuple[List[str], List[str]]:
    mics: List[str] = []
    sys_devs: List[str] = []
    try:
        r = subprocess.run(['pactl', 'list', 'sources', 'short'],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]
                (sys_devs if 'monitor' in name.lower() else mics).append(name)
    except Exception:
        pass
    return mics, sys_devs


# ── Segment thread ────────────────────────────────────────────────────────────

class _SegmentThread(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, cmd: List[str], output: str, parent=None):
        super().__init__(parent)
        self._cmd = cmd
        self._output = output
        self._proc: Optional[subprocess.Popen] = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._proc.wait()
            self.done.emit(self._output)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
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
