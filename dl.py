import sys
from module.fetch import try_download_loop
from module.config import DOWNLOAD_DIR

def main():
    if any(arg.lower() in ("-s", "--server") for arg in sys.argv[1:]):
        from module.server import app
        print("[*] Starting Flask server...")
        app.run(host='127.0.0.1', port=7601)
        return

    try_download_loop()
    print("[*] All tasks completed.")

if __name__ == "__main__":
    main()
