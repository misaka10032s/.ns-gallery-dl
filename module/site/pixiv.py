import json
import subprocess
from pathlib import Path
from ..tokens import save_tokens

def get_pixiv_token(tokens):
    """檢查或取得 Pixiv refresh token"""
    if "pixiv_refresh_token" in tokens and tokens["pixiv_refresh_token"]:
        return tokens["pixiv_refresh_token"]

    print("[Pixiv] 未找到 refresh token，執行認證流程...")
    try:
        subprocess.run(["gallery-dl", "oauth:pixiv"], check=True)
    except subprocess.CalledProcessError:
        print("[Pixiv] 認證流程執行失敗")
        return None

    config_path = Path.home() / ".config" / "gallery-dl" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            refresh_token = cfg.get("extractor", {}).get("pixiv", {}).get("refresh-token", "")
            if refresh_token:
                tokens["pixiv_refresh_token"] = refresh_token
                save_tokens(tokens)
                print("[Pixiv] refresh token 已儲存到 token.json")
                return refresh_token
        except Exception as e:
            print(f"[Pixiv] 無法讀取 config.json: {e}")

    print("[Pixiv] 無法取得 refresh token")
    return None
