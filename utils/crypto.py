"""
Fernet暗号化・復号ユーティリティ。
初回起動時にFernetキーを生成してkey.binに保存し、
以降はkey.binを読み込んで使い回す。
"""

import os
from cryptography.fernet import Fernet


# key.binの保存先（exeと同じフォルダ）
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "key.bin")


def _get_key_path() -> str:
    """key.binの絶対パスを返す。"""
    return os.path.normpath(KEY_FILE)


def load_or_create_key() -> bytes:
    """
    Fernetキーを返す。
    key.binが存在しない場合は新規生成して保存する。
    """
    key_path = _get_key_path()
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
        return key


def encrypt(data: str) -> bytes:
    """
    文字列をFernetで暗号化してbytesを返す。

    Args:
        data: 暗号化する文字列

    Returns:
        暗号化されたbytes
    """
    key = load_or_create_key()
    f = Fernet(key)
    return f.encrypt(data.encode("utf-8"))


def decrypt(token: bytes) -> str:
    """
    Fernet暗号化されたbytesを復号して文字列を返す。

    Args:
        token: 暗号化されたbytes

    Returns:
        復号された文字列
    """
    key = load_or_create_key()
    f = Fernet(key)
    return f.decrypt(token).decode("utf-8")
