# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para "Goujana Agenda"
# Build: pyinstaller build/alertas.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

import os
import sys
_root = os.path.abspath(os.path.join(SPECPATH, '..'))

# Incluir python312.dll explícitamente para evitar "Failed to load Python DLL"
_py_dll = os.path.join(os.path.dirname(sys.executable), 'python312.dll')
_extra_binaries = [(_py_dll, '.')] if os.path.exists(_py_dll) else []

a = Analysis(
    [os.path.join(_root, 'main.py')],
    pathex=[_root],
    binaries=_extra_binaries,
    datas=[
        (os.path.join(_root, 'assets', 'icon.png'), 'assets'),
        (os.path.join(_root, 'assets', 'icon.ico'), 'assets'),
    ] + collect_data_files('groq') + collect_data_files('httpx') + collect_data_files('certifi'),
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'urllib3',
        'requests',
        'certifi',
        'charset_normalizer',
        'idna',
        'groq',
        'httpx',
        'httpcore',
        'anyio',
        'sniffio',
        'distro',
    ] + collect_submodules('groq') + collect_submodules('httpx'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'torch', 'tensorflow',
              'faster_whisper', 'ctranslate2', 'tokenizers'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Goujana Agenda',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(_root, 'assets', 'icon.ico'),
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Goujana Agenda',
)
