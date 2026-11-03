"""Lazy dashboard launch; optional dependencies never enter core SDK imports."""

import threading
import webbrowser
from pathlib import Path

from thadam.terminal import TerminalStyle


def launch(
    root: Path, *, port: int = 8765, open_browser: bool = True, style: TerminalStyle | None = None
) -> None:
    """Serve one project on loopback until interrupted, closing active workers on exit."""
    try:
        import uvicorn

        from thadam.dashboard.server import create_app
    except ImportError as error:
        raise ValueError(
            "Dashboard dependencies are missing. Install thadam-ai[dashboard] (from a checkout: python -m pip install -e '.[dashboard]')."
        ) from error
    app = create_app(root)
    address = f"http://127.0.0.1:{port}/#token={app.state.token}"
    style = style or TerminalStyle()
    print(
        "\n"
        + style.paint("  THADAM · Local dashboard", "brand", bold=True)
        + "\n"
        + style.paint(f"  Project: {root.resolve()}", "info")
        + "\n\n"
        + style.paint(f"  {address}", "brand")
        + "\n\n  Keep this terminal open. Press Ctrl+C to stop.\n",
        flush=True,
    )
    if open_browser:
        timer = threading.Timer(1, lambda: webbrowser.open(address))
        timer.daemon = True
        timer.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
    except SystemExit as error:
        if error.code:
            raise ValueError(
                "Could not start the local dashboard. Check the folder and choose an available --port."
            ) from error
    finally:
        if open_browser:
            timer.cancel()
