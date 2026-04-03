"""
settings.json の読み書き。スロットごとの設定を平文JSONで保管する。
"""

import json
import os

_BASE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
SETTINGS_FILE = os.path.join(_BASE, "settings.json")

# スロット1件分のデフォルト値
DEFAULT_SLOT: dict = {
    "enabled": False,
    "url": "https://",
    "scroll_interval": 3.0,
    "scroll_count": 10,
    "refresh_interval": 60.0,
    "username": "",
    "password": "",
}


def load_settings() -> dict:
    """
    settings.json を読み込んで返す。
    存在しない・破損している場合はデフォルト値を返す。
    """
    if not os.path.exists(SETTINGS_FILE):
        return {"slot_count": 5, "slots": {}}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"slot_count": 5, "slots": {}}


def save_settings(data: dict) -> None:
    """設定辞書全体を settings.json に保存する。"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_slot(data: dict, slot: int) -> dict:
    """
    指定スロットの設定を返す。
    未保存のキーはデフォルト値で補完する。
    """
    merged = DEFAULT_SLOT.copy()
    merged.update(data.get("slots", {}).get(str(slot), {}))
    return merged


def save_slot(slot: int, config: dict) -> None:
    """指定スロットの設定だけを更新して保存する。"""
    data = load_settings()
    if "slots" not in data:
        data["slots"] = {}
    data["slots"][str(slot)] = config
    save_settings(data)
