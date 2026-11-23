"""Start the local web app and open it in the default browser."""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from app import app


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", 8000))
            return 8000
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def open_browser(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    port = choose_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    print(f"Işläp başlady: {url}")
    print("Platformany ýapmak üçin bu penjiräni ýaňyň ýa-da Ctrl+C düwmesine basyň.")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
