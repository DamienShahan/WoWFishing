# Build with: python -m PyInstaller --noconfirm WoWFishing.spec
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=collect_data_files('customtkinter') + [
        ('sounds/target/*.wav', 'sounds/target'),
        ('assets/wowfishing.png', 'assets'),
        ('assets/wowfishing.ico', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Legacy-only/scientific development packages are not part of this app.
    excludes=['librosa', 'numba', 'llvmlite', 'matplotlib', 'pandas', 'IPython', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='WoWFishing',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, icon='assets/wowfishing.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='WoWFishing')
