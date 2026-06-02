"""OS microphone volume control — Windows Core Audio + Linux pactl.

get_mic_volume() → float 0.0–1.0
set_mic_volume(float)      — affects all apps immediately

No extra dependencies: Windows uses ctypes COM; Linux uses pactl subprocess.
"""
import subprocess
import sys

# ── Windows: IAudioEndpointVolume via ctypes ──────────────────────────────────
if sys.platform == 'win32':
    import ctypes
    import uuid as _uuid

    class _GUID(ctypes.Structure):
        _fields_ = [
            ('Data1', ctypes.c_uint32), ('Data2', ctypes.c_uint16),
            ('Data3', ctypes.c_uint16), ('Data4', ctypes.c_uint8 * 8),
        ]

    def _g(s: str) -> '_GUID':
        u = _uuid.UUID(s)
        b = u.bytes_le
        g = _GUID()
        g.Data1 = int.from_bytes(b[0:4], 'little')
        g.Data2 = int.from_bytes(b[4:6], 'little')
        g.Data3 = int.from_bytes(b[6:8], 'little')
        for i in range(8):
            g.Data4[i] = b[8 + i]
        return g

    class _WinVolCtrl:
        """IAudioEndpointVolume wrapper for the default capture device."""
        _CLSCTX = 23
        _eCapture = 1
        _eConsole = 0

        # IAudioEndpointVolume vtable:
        #  0 QueryInterface  1 AddRef  2 Release
        #  3 RegisterControlChangeNotify  4 UnregisterControlChangeNotify
        #  5 SetMasterVolumeLevel   6 SetMasterVolumeLevelScalar
        #  7 GetMasterVolumeLevel   8 GetMasterVolumeLevelScalar

        def __init__(self):
            self._ptr = 0
            self._sz  = ctypes.sizeof(ctypes.c_void_p)
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

        def _rel(self, obj: int):
            self._fn(obj, 2)(obj)

        def _open(self):
            ole32 = ctypes.windll.ole32
            CLSID = _g('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
            IID_E = _g('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
            IID_V = _g('{5CDF2C82-841E-4546-9722-0CF74078229A}')

            e = ctypes.c_void_p()
            if ole32.CoCreateInstance(
                ctypes.byref(CLSID), None, self._CLSCTX,
                ctypes.byref(IID_E), ctypes.byref(e),
            ) < 0 or not e.value:
                return

            d = ctypes.c_void_p()
            hr = self._fn(e.value, 4,
                          ctypes.c_int, ctypes.c_int,
                          ctypes.POINTER(ctypes.c_void_p))(
                e.value, self._eCapture, self._eConsole, ctypes.byref(d))
            self._rel(e.value)
            if hr < 0 or not d.value:
                return

            v = ctypes.c_void_p()
            hr = self._fn(d.value, 3,
                          ctypes.POINTER(_GUID), ctypes.c_uint,
                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                d.value, ctypes.byref(IID_V), self._CLSCTX, None, ctypes.byref(v))
            self._rel(d.value)
            if hr >= 0 and v.value:
                self._ptr = v.value

        def get(self) -> float:
            if not self._ptr:
                return 0.8
            val = ctypes.c_float()
            hr  = self._fn(self._ptr, 8, ctypes.POINTER(ctypes.c_float))(
                self._ptr, ctypes.byref(val))
            return max(0.0, min(1.0, val.value)) if hr >= 0 else 0.8

        def set(self, level: float):
            if not self._ptr:
                return
            self._fn(self._ptr, 6, ctypes.c_float, ctypes.c_void_p)(
                self._ptr, ctypes.c_float(max(0.0, min(1.0, level))), None)

        def close(self):
            if self._ptr:
                self._rel(self._ptr)
                self._ptr = 0

    _ctrl: '_WinVolCtrl | None' = None

    def _get_ctrl() -> '_WinVolCtrl':
        global _ctrl
        if _ctrl is None:
            _ctrl = _WinVolCtrl()
        return _ctrl


# ── Public API ────────────────────────────────────────────────────────────────

def get_mic_volume() -> float:
    """Return current OS microphone volume as 0.0–1.0."""
    if sys.platform == 'win32':
        return _get_ctrl().get()
    try:
        import re
        r = subprocess.run(
            ['pactl', 'get-source-volume', '@DEFAULT_SOURCE@'],
            capture_output=True, text=True, timeout=3,
        )
        m = re.search(r'/\s*(\d+)%', r.stdout)
        return float(m.group(1)) / 100.0 if m else 0.8
    except Exception:
        return 0.8


def set_mic_volume(level: float):
    """Set OS microphone volume (0.0–1.0). Affects all apps using the mic."""
    level = max(0.0, min(1.0, level))
    if sys.platform == 'win32':
        _get_ctrl().set(level)
    else:
        try:
            pct = int(round(level * 100))
            subprocess.run(
                ['pactl', 'set-source-volume', '@DEFAULT_SOURCE@', f'{pct}%'],
                timeout=3,
            )
        except Exception:
            pass
