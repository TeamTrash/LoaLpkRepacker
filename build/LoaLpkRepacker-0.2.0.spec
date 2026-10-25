# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Codex/Desktop/Loa-research/apps/LoaLpkRepacker/app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Codex/Desktop/Loa-research/apps/LoaLpkRepacker/backend', 'backend')],
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
    name='LoaLpkRepacker-0.2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
