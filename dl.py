import sys
import subprocess

def _bootstrap() -> None:
    """Ensure all Python dependencies are installed before importing project modules."""
    try:
        import dotenv   # noqa: F401
        import discord  # noqa: F401
        import flask    # noqa: F401
        import tqdm     # noqa: F401
    except ImportError as e:
        print(f"[!] Missing dependency detected: {e}")
        print("[*] Installing from requirements.txt ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=False,
        )
        if result.returncode != 0:
            print("[!] Auto-install failed. Please run manually:")
            print("    pip install -r requirements.txt")
            sys.exit(1)
        # Re-exec so the newly installed modules are available
        import os
        os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

import threading
from module.fetch import try_download_loop
from module.config import DOWNLOAD_DIR

def _start_server_thread():
    from module.server import app
    print("[*] Starting Flask server on port 7601...")
    # use_reloader=False is required when running inside a thread
    app.run(host='127.0.0.1', port=7601, use_reloader=False)

def main():
    args = sys.argv[1:]
    server_mode = any(arg.lower() in ("-s", "--server") for arg in args)
    bot_mode    = any(arg.lower() in ("-b", "--bot")    for arg in args)

    if server_mode and bot_mode:
        # Run Flask in a background thread; Discord bot takes the main thread
        t = threading.Thread(target=_start_server_thread, daemon=True)
        t.start()
        from module.bot.dc import run as run_bot
        run_bot()
        return

    if server_mode:
        _start_server_thread()
        return

    if bot_mode:
        from module.bot.dc import run as run_bot
        run_bot()
        return

    try_download_loop()
    print("[*] All tasks completed.")

if __name__ == "__main__":
    main()
