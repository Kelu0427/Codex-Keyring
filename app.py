from __future__ import annotations

from pathlib import Path

import webview

from api import Api
from constants import APP_NAME


def main() -> None:
    root = Path(__file__).resolve().parent
    webview.create_window(
        APP_NAME,
        str(root / "web" / "index.html"),
        js_api=Api(),
        width=1240,
        height=820,
        min_size=(940, 640),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
