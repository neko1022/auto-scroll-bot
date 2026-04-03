"""
1スロット分の Chrome 起動・手動ログイン待機・スクロールループを担うクラス。
undetected-chromedriver でbot検知を回避する。
プロファイルは profiles/slot{n}/ に保存してセッションを再利用する。
"""

import os
import re
import subprocess
import time
import threading
from typing import Callable

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import WebDriverException

# プロファイル保存先
_BASE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
PROFILES_DIR = os.path.join(_BASE, "profiles")

# 手動ログイン待機の最大秒数（5分）
MANUAL_LOGIN_TIMEOUT = 300

# 通常のChromeと同じUser-Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# 複数スレッドの同時初期化競合を防ぐロック
_driver_init_lock = threading.Lock()


def _get_chrome_version() -> int | None:
    """
    Windowsレジストリからインストール済みChromeのメジャーバージョンを返す。
    取得できない場合は None を返す。
    """
    reg_paths = [
        r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon",
    ]
    for path in reg_paths:
        try:
            r = subprocess.run(
                ["reg", "query", path, "/v", "version"],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r"(\d+)\.\d+\.\d+\.\d+", r.stdout)
            if m:
                return int(m.group(1))
        except Exception:
            continue
    return None


class BrowserBot:
    """
    1スロット分の自動操作ボット。
    ログイン待機・スクロール・F5更新を独立したスレッドで実行する。
    """

    def __init__(
        self,
        slot: int,
        url: str,
        scroll_interval: float,
        scroll_count: int,
        refresh_interval: float,
        log_callback: Callable[[str], None],
    ):
        """
        Args:
            slot: スロット番号（1〜10）
            url: スクロール対象URL
            scroll_interval: PageDown間隔（秒）
            scroll_count: PageDown回数
            refresh_interval: F5更新までの待機時間（秒）
            log_callback: ログ出力コールバック
        """
        self.slot = slot
        self.url = url
        self.scroll_interval = scroll_interval
        self.scroll_count = scroll_count
        self.refresh_interval = refresh_interval
        self._log_cb = log_callback
        self.driver: uc.Chrome | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """スロット番号付きでログを出力する。"""
        self._log_cb(f"スロット{self.slot}: {message}")

    def _is_stopped(self) -> bool:
        """停止フラグが立っているか返す。"""
        return self._stop_event.is_set()

    def _sleep(self, seconds: float) -> bool:
        """
        指定秒スリープする。停止フラグで即座に抜ける。

        Returns:
            True: 完了 / False: 停止フラグで中断
        """
        end = time.time() + seconds
        while time.time() < end:
            if self._is_stopped():
                return False
            time.sleep(0.3)
        return True

    # ------------------------------------------------------------------
    # Chrome起動
    # ------------------------------------------------------------------

    def _build_driver(self) -> uc.Chrome:
        """
        専用プロファイル付きのChromeを起動して返す。
        ロックで直列化し複数スロットの同時初期化競合を防ぐ。
        """
        profile_dir = os.path.join(PROFILES_DIR, f"slot{self.slot}")
        os.makedirs(profile_dir, exist_ok=True)

        options = uc.ChromeOptions()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")

        ver = _get_chrome_version()
        if ver:
            self._log(f"Chrome {ver} を検出")
        else:
            self._log("Chromeバージョン自動検出に失敗しました")

        with _driver_init_lock:
            driver = uc.Chrome(
                options=options,
                user_data_dir=profile_dir,
                version_main=ver,
            )
        return driver

    # ------------------------------------------------------------------
    # ログイン状態確認
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """
        現在のページがログイン済みかをURLとDOMで判定する。
        ログインページにいる場合・ナビバーDOMが存在しない場合は False を返す。
        """
        try:
            url = self.driver.current_url
            if any(p in url for p in ("login", "i/flow", "signin")):
                return False
            elems = self.driver.find_elements(
                By.CSS_SELECTOR, '[data-testid="AppTabBar_Home_Link"]'
            )
            return len(elems) > 0
        except WebDriverException:
            return False

    def _wait_for_login(self) -> bool:
        """
        手動ログインが完了するまでポーリングで待機する（最大5分）。

        Returns:
            True: ログイン完了 / False: タイムアウトまたは停止
        """
        deadline = time.time() + MANUAL_LOGIN_TIMEOUT
        while time.time() < deadline:
            if self._is_stopped():
                return False
            if self._is_logged_in():
                self._log("✅ ログイン完了を確認しました")
                return True
            time.sleep(3)
        self._log("❌ ログイン待機タイムアウト（5分）")
        return False

    # ------------------------------------------------------------------
    # スクロールループ
    # ------------------------------------------------------------------

    def _scroll_loop(self) -> None:
        """
        以下を停止ボタンが押されるまで無限に繰り返す。

        ループ:
          1. PageDown を scroll_interval 秒ごとに scroll_count 回押す
          2. refresh_interval 秒待つ
          3. ページを更新してトップへ戻る
          4. 1 に戻る
        """
        self._log("スクロール動作を開始します")

        while not self._is_stopped():

            # Step 1: PageDown × scroll_count 回（間隔: scroll_interval 秒）
            for _ in range(self.scroll_count):
                if self._is_stopped():
                    return
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
                except WebDriverException:
                    pass
                if not self._sleep(self.scroll_interval):
                    return

            # Step 2: refresh_interval 秒待つ
            if not self._sleep(self.refresh_interval):
                return

            # Step 3: ページ更新 → トップへ戻る
            if self._is_stopped():
                return
            try:
                self._log("🔄 更新")
                self.driver.refresh()
                time.sleep(3)
                self.driver.execute_script("window.scrollTo(0, 0)")
            except WebDriverException:
                pass

            # → Step 1 に戻る

    # ------------------------------------------------------------------
    # 公開インターフェース
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        ボットのメイン処理。
        1. Chrome起動（専用プロファイル）
        2. x.com/login に遷移
        3. セッション継続またはログイン完了を確認
        4. 対象URLへ遷移
        5. スクロールループ（無限）
        """
        self._stop_event.clear()
        try:
            self._log("Chrome 起動中...")
            self.driver = self._build_driver()

            self._log("https://x.com/login に遷移します...")
            self.driver.get("https://x.com/login")
            time.sleep(3)

            if self._is_logged_in():
                self._log("✅ 既存セッションでログイン済み")
            else:
                self._log("⚠️ 手動でログインしてください。完了を自動検知します...")
                if not self._wait_for_login():
                    return

            self._log(f"対象URLへ遷移: {self.url}")
            self.driver.get(self.url)
            time.sleep(3)

            self._scroll_loop()

        except WebDriverException as e:
            self._log(f"❌ ブラウザエラー: {e}")
        except Exception as e:
            self._log(f"❌ エラー: {e}")
        finally:
            self._quit()

    def stop(self) -> None:
        """停止フラグを立てる。"""
        self._stop_event.set()

    def _quit(self) -> None:
        """Chromeドライバを安全に終了する。"""
        if self.driver:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None
        self._log("停止しました")
