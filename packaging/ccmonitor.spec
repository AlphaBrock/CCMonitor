# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Usage Monitor for Claude.

Build:
  pyinstaller packaging/ccmonitor.spec
"""
from pathlib import Path

ROOT = Path.cwd()

a = Analysis(
    [str(ROOT / 'src' / '__main__.py')],
    pathex=[],
    binaries=[],
    datas=[
        (str(ROOT / 'locale' / '*.json'), 'locale'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.html'), 'src/ui/popup'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.css'), 'src/ui/popup'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.js'), 'src/ui/popup'),
    ],
    hiddenimports=[
        'pystray._win32',
        'pystray._util',
        'pystray._util.win32',
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        'bottle',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'unittest', 'test',
        'xmlrpc', 'pydoc',
        'tkinter', '_tkinter',
        'PIL._avif', 'PIL._webp',
        'PIL._imagingcms', 'PIL._imagingmath', 'PIL._imagingtk', 'PIL._imagingmorph',
        'PIL.BlpImagePlugin', 'PIL.BufrStubImagePlugin', 'PIL.CurImagePlugin', 'PIL.DcxImagePlugin',
        'PIL.DdsImagePlugin', 'PIL.EpsImagePlugin', 'PIL.FitsImagePlugin', 'PIL.FliImagePlugin',
        'PIL.FpxImagePlugin', 'PIL.FtexImagePlugin', 'PIL.GbrImagePlugin', 'PIL.GribStubImagePlugin',
        'PIL.Hdf5StubImagePlugin', 'PIL.IcnsImagePlugin', 'PIL.ImImagePlugin', 'PIL.ImtImagePlugin',
        'PIL.IptcImagePlugin', 'PIL.Jpeg2KImagePlugin', 'PIL.McIdasImagePlugin', 'PIL.MicImagePlugin',
        'PIL.MpegImagePlugin', 'PIL.MpoImagePlugin', 'PIL.MspImagePlugin', 'PIL.PalmImagePlugin',
        'PIL.PcdImagePlugin', 'PIL.PdfImagePlugin', 'PIL.PixarImagePlugin', 'PIL.PsdImagePlugin',
        'PIL.QoiImagePlugin', 'PIL.SgiImagePlugin', 'PIL.SpiderImagePlugin', 'PIL.SunImagePlugin',
        'PIL.TgaImagePlugin', 'PIL.WalImagePlugin', 'PIL.WmfImagePlugin', 'PIL.XbmImagePlugin',
        'PIL.XpmImagePlugin', 'PIL.XVThumbImagePlugin',
        'setuptools', '_distutils_hack',
        'asyncio', 'concurrent',
        'multiprocessing',
        'xml', 'tomllib',
        'sqlite3',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UsageMonitorForClaude',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(ROOT / 'assets' / 'usage_monitor_for_claude.ico'),
    version=str(ROOT / 'packaging' / 'version_info.py'),
)
