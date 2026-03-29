# -*- mode: python ; coding: utf-8 -*-
import os
HERE = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(HERE, 'lust_client.py')],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='lust-client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(HERE, 'assets', 'icons', 'onyx.ico')],
)
