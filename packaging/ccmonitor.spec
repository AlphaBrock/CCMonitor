# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for CCMonitor.

Build:
  pyinstaller packaging/ccmonitor.spec
"""
from pathlib import Path

ROOT = Path.cwd()


def keep_packaged_resource(entry):
    target = str(entry[0]).replace('\\', '/').lower()
    blocked_targets = (
        'webview/lib/runtimes/win-x86/native/webview2loader.dll',
        'webview/lib/runtimes/win-arm64/native/webview2loader.dll',
        'webview/lib/pywebview-android.jar',
        'webview/lib/webbrowserinterop.x86.dll',
        'webview/lib/webbrowserinterop.x64.dll',
        'clr_loader/ffi/dlls/x86/',
    )
    return not any(blocked_target in target for blocked_target in blocked_targets)


a = Analysis(
    [str(ROOT / 'src' / '__main__.py')],
    pathex=[],
    binaries=[],
    datas=[
        (str(ROOT / 'locale' / '*.json'), 'locale'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.html'), 'src/ui/popup'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.css'), 'src/ui/popup'),
        (str(ROOT / 'src' / 'ui' / 'popup' / 'popup.js'), 'src/ui/popup'),
        (str(ROOT / 'assets' / 'icon' / '*.svg'), 'assets/icon'),
        (str(ROOT / 'packaging' / 'runtime_dir.keep'), 'webview/lib/runtimes/win-arm64/native'),
        (str(ROOT / 'packaging' / 'runtime_dir.keep'), 'webview/lib/runtimes/win-x86/native'),
    ],
    hiddenimports=[
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
        'setuptools', '_distutils_hack',
        'asyncio', 'concurrent',
        'multiprocessing',
        'xml', 'tomllib',
        'sqlite3',
        'webview.platforms.android',
        'webview.platforms.cocoa',
        'webview.platforms.gtk',
        'webview.platforms.qt',
        'webview.platforms.cef',
        'webview.platforms.mshtml',
        'urllib3.contrib.emscripten',
        'urllib3.contrib.pyopenssl',
        'urllib3.contrib.socks',
        'urllib3.http2.connection',
        'idna.uts46data',
    ],
    noarchive=False,
    optimize=2,
)

a.binaries = [entry for entry in a.binaries if keep_packaged_resource(entry)]
a.datas = [entry for entry in a.datas if keep_packaged_resource(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CCMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(ROOT / 'assets' / 'ccmonitor.ico'),
    version=str(ROOT / 'packaging' / 'version_info.py'),
)
