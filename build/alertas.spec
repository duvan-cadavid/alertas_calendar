# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para "Alertas de Calendarios"
# Build: pyinstaller build/alertas.spec

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

import os
import sys
_root = os.path.abspath(os.path.join(SPECPATH, '..'))

# Incluir python312.dll explícitamente para evitar "Failed to load Python DLL"
_py_dll = os.path.join(os.path.dirname(sys.executable), 'python312.dll')
_extra_binaries = [(_py_dll, '.')] if os.path.exists(_py_dll) else []

# ── faster-whisper + ctranslate2 + tokenizers ────────────────────
datas_fw,  bins_fw,  hidden_fw  = collect_all('faster_whisper')
datas_ct,  bins_ct,  hidden_ct  = collect_all('ctranslate2')
datas_tk,  bins_tk,  hidden_tk  = collect_all('tokenizers')
datas_hf,  bins_hf,  hidden_hf  = collect_all('huggingface_hub')
datas_av,  bins_av,  hidden_av  = collect_all('av')

a = Analysis(
    [os.path.join(_root, 'main.py')],
    pathex=[_root],
    binaries=_extra_binaries + bins_fw + bins_ct + bins_tk + bins_hf + bins_av,
    datas=[
        (os.path.join(_root, 'assets', 'icon.png'), 'assets'),
        (os.path.join(_root, 'assets', 'icon.ico'), 'assets'),
    ] + datas_fw + datas_ct + datas_tk + datas_hf + datas_av,
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
        'faster_whisper',
        'ctranslate2',
        'tokenizers',
        'huggingface_hub',
        'av',
        'tqdm',
        'filelock',
        'packaging',
    ] + hidden_fw + hidden_ct + hidden_tk + hidden_hf + hidden_av,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'torch', 'tensorflow'],
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
    name='Alertas de Calendarios',
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
    name='Alertas de Calendarios',
)
