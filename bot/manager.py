"""
有効なスロット設定を受け取り、BrowserBot を並列スレッドで管理するマネージャー。
"""

import threading
from typing import Callable

from bot.browser_bot import BrowserBot


class BotManager:
    """最大10スロットのBrowserBotを並列起動・停止する。"""

    def __init__(self) -> None:
        self._bots: list[BrowserBot] = []
        self._threads: list[threading.Thread] = []

    def start(self, slot_configs: list[dict], log_callback: Callable[[str], None]) -> None:
        """
        有効スロット分のBrowserBotをスレッドで起動する。

        Args:
            slot_configs: 有効スロットの設定リスト。各要素は以下のキーを持つ。
                          {"slot", "url", "scroll_interval", "scroll_count", "refresh_interval"}
            log_callback: ログ出力コールバック
        """
        self._bots.clear()
        self._threads.clear()

        for cfg in slot_configs:
            bot = BrowserBot(
                slot=cfg["slot"],
                url=cfg["url"],
                scroll_interval=cfg["scroll_interval"],
                scroll_count=cfg["scroll_count"],
                refresh_interval=cfg["refresh_interval"],
                log_callback=log_callback,
            )
            self._bots.append(bot)
            t = threading.Thread(target=bot.run, daemon=True, name=f"bot-slot{cfg['slot']}")
            self._threads.append(t)
            t.start()

        log_callback(f"▶ {len(slot_configs)} 件のインスタンスを起動しました")

    def stop(self) -> None:
        """全ボットに停止シグナルを送る。"""
        for bot in self._bots:
            bot.stop()

    def is_running(self) -> bool:
        """いずれかのスレッドが実行中かどうかを返す。"""
        return any(t.is_alive() for t in self._threads)
