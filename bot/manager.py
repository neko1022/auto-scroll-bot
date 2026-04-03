"""
複数BrowserBotインスタンスをスレッドで並列管理するマネージャー。
"""

import threading
from typing import Callable

from bot.browser_bot import BrowserBot


class BotManager:
    """
    最大5つのBrowserBotを並列起動・停止するマネージャー。
    """

    def __init__(self, log_callback: Callable[[str], None]):
        """
        Args:
            log_callback: ログ出力コールバック関数。BrowserBotに渡される。
        """
        self.log_callback = log_callback
        self._bots: list[BrowserBot] = []
        self._threads: list[threading.Thread] = []

    def start(
        self,
        accounts: list[dict],
        target_url: str,
        scroll_interval: float,
        scroll_count: int,
        refresh_interval: float,
    ) -> None:
        """
        指定されたアカウント数分のBrowserBotをスレッドで起動する。

        Args:
            accounts: [{"username": str, "password": str}, ...] のリスト
            target_url: スクロール対象URL
            scroll_interval: PageDown間隔（秒）
            scroll_count: PageDown回数
            refresh_interval: F5更新までの時間（秒）
        """
        self._bots.clear()
        self._threads.clear()

        for i, account in enumerate(accounts, start=1):
            bot = BrowserBot(
                index=i,
                username=account.get("username", ""),
                password=account.get("password", ""),
                target_url=target_url,
                scroll_interval=scroll_interval,
                scroll_count=scroll_count,
                refresh_interval=refresh_interval,
                log_callback=self.log_callback,
            )
            self._bots.append(bot)

            thread = threading.Thread(target=bot.run, daemon=True, name=f"bot-{i}")
            self._threads.append(thread)
            thread.start()

        self.log_callback(f"▶ {len(accounts)}件のインスタンスを起動しました")

    def stop(self) -> None:
        """全BrowserBotに停止シグナルを送る。"""
        for bot in self._bots:
            bot.stop()
        self.log_callback("■ 全インスタンスに停止シグナルを送信しました")

    def is_running(self) -> bool:
        """いずれかのスレッドが実行中かどうかを返す。"""
        return any(t.is_alive() for t in self._threads)
