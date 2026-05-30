"""
Entry Point
===========

Application entry point, shared by ``python -m src`` and the root ``main.py``.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import traceback
from collections.abc import Sequence
from typing import Any


def _verbose_step(label: str, verbose: bool) -> None:
    """Print a startup step when verbose mode is enabled."""
    if verbose:
        print(f'  [startup] {label}', flush=True)


def _configure_startup(verbose: bool) -> None:
    """Complete startup configuration before importing GUI components.

    Parameters
    ----------
    verbose : bool
        Whether to enable verbose diagnostic output.
    """
    if verbose and getattr(sys, 'frozen', False):
        from src.runtime.verbose import setup_console

        setup_console()

    # Must run before pywebview's internal DPI call, otherwise menu hover breaks on high-DPI.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))

    # Enable dark mode for native context menus to match the dark UI theme.
    # uxtheme ordinal 135 = SetPreferredAppMode(AllowDark=1), 136 = FlushMenuThemes.
    try:
        ctypes.windll.uxtheme[135](1)
        ctypes.windll.uxtheme[136]()
    except Exception:
        pass

    if verbose:
        from src.runtime.verbose import print_startup_diagnostics

        print_startup_diagnostics()


def main(argv: Sequence[str] | None = None) -> None:
    """Run the main application flow.

    Parameters
    ----------
    argv : Sequence[str] or None, optional
        Command-line arguments.  Defaults to ``sys.argv[1:]`` when ``None``.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    verbose = '--verbose' in arguments
    result: dict[str, Any] = {}

    _configure_startup(verbose)

    import webview  # type: ignore[import-untyped]  # no type stubs available

    from src.runtime.app import CCMonitor, crash_log
    from src.runtime.single_instance import ensure_single_instance, release_instance_lock

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s %(levelname)-5s %(name)s: %(message)s',
            datefmt='%H:%M:%S',
        )

    def _run_app() -> None:
        """Run the tray application in a background thread."""
        try:
            if verbose:
                from src.runtime.verbose import print_runtime_diagnostics

                print_runtime_diagnostics()

            _verbose_step('CCMonitor()...', verbose)
            app = CCMonitor()
            _verbose_step('CCMonitor()... OK', verbose)

            _verbose_step('app.run...', verbose)
            app.run()
            result['app'] = app
        except Exception:
            error = traceback.format_exc()
            _verbose_step(f'CRASH: {error}', verbose)
            crash_log(error)
        finally:
            # Destroy the hidden keep-alive window and all popups so webview.start() returns.
            for window in list(webview.windows):
                try:
                    window.destroy()
                except Exception:
                    pass

    try:
        _verbose_step('ensure_single_instance...', verbose)
        if not ensure_single_instance():
            _verbose_step('another instance is running, exiting', verbose)
            return
        _verbose_step('ensure_single_instance... OK', verbose)

        # pywebview's GUI event loop must run on the main thread.
        # This hidden window keeps the loop alive; the tray logic runs in a background thread.
        _verbose_step('webview.create_window...', verbose)
        webview.create_window('', html='', hidden=True)
        _verbose_step('webview.create_window... OK', verbose)

        _verbose_step('webview.start...', verbose)
        webview.start(func=_run_app)
        _verbose_step('webview.start returned', verbose)

        app = result.get('app')
        if app and app.restart_requested:
            release_instance_lock()

            if getattr(sys, 'frozen', False):
                # Strip PyInstaller temp env vars so the restarted process doesn't reuse the old extraction dir.
                environment = {key: value for key, value in os.environ.items() if not key.startswith(('_PYI_', '_MEI'))}
                subprocess.Popen(
                    [sys.executable],
                    env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen(
                    [sys.executable, '-m', 'src'],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
    except Exception:
        crash_log(traceback.format_exc())


if __name__ == '__main__':
    main()
