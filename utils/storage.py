"""
accounts.json（Fernet暗号化）と settings.json（平文）の読み書き。
"""

import json
import os
from typing import Any

from utils.crypto import encrypt, decrypt

# ファイルの保存先（exeと同じフォルダ）
_BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ACCOUNTS_FILE = os.path.join(_BASE_DIR, "accounts.json")
SETTINGS_FILE = os.path.join(_BASE_DIR, "settings.json")


# ---- アカウント情報 --------------------------------------------------------

def save_accounts(accounts: list[dict]) -> None:
    """
    アカウントリストをFernet暗号化してaccounts.jsonに保存する。

    Args:
        accounts: [{"username": str, "password": str}, ...] の形式のリスト
    """
    raw = json.dumps(accounts, ensure_ascii=False)
    token = encrypt(raw)
    with open(ACCOUNTS_FILE, "wb") as f:
        f.write(token)


def load_accounts() -> list[dict]:
    """
    accounts.jsonを復号してアカウントリストを返す。
    ファイルが存在しない・復号失敗の場合は空リストを返す。

    Returns:
        [{"username": str, "password": str}, ...] の形式のリスト
    """
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "rb") as f:
            token = f.read()
        raw = decrypt(token)
        return json.loads(raw)
    except Exception:
        return []


# ---- 設定情報 ----------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    "url": "https://",
    "scroll_interval": 3,
    "scroll_count": 5,
    "refresh_interval": 60,
    "instance_count": 1,
}


def save_settings(settings: dict) -> None:
    """
    設定辞書をsettings.jsonに平文で保存する。

    Args:
        settings: 設定辞書
    """
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_settings() -> dict:
    """
    settings.jsonを読み込んで設定辞書を返す。
    ファイルが存在しない場合はデフォルト値を返す。

    Returns:
        設定辞書
    """
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # デフォルト値で欠損キーを補完
        merged = DEFAULT_SETTINGS.copy()
        merged.update(data)
        return merged
    except Exception:
        return DEFAULT_SETTINGS.copy()
