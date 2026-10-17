# PyInstaller spec: run from project root with `pyinstaller FF14-Accessory-Adapter.spec`
# Tkinter and all current GUI/package-builder dependencies are Python standard library.
block_cipher = None

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
PROJECT_ROOT = Path(SPECPATH).resolve()
SRC_DIR = PROJECT_ROOT / 'src'
sys.path.insert(0, str(SRC_DIR))
hiddenimports = collect_submodules('accessory_adapter')

a = Analysis(
    ['run_gui.py'],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    name='FF14-Accessory-Adapter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
