"""
単一Chromeインスタンスのログイン待機・スクロール・F5更新を担うクラス。
undetected-chromedriver を使用してbot検知を回避する。
ログインは手動で行い、完了を検知してからスクロールを開始する。
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
_BASE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
PROFILES_DIR = os.path.join(_BASE_DIR, "profiles")

# 手動ログイン待機の最大秒数
MANUAL_AUTH_TIMEOUT = 300  # 5分

# 通常のChromeと同じUser-Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _get_chrome_major_version() -> int | None:
    """
    インストール済みChromeのメジャーバージョン番号を返す。
    Windowsレジストリから取得し、失敗した場合はNoneを返す。
    """
    reg_paths = [
        r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon",
    ]
    for path in reg_paths:
        try:
            result = subprocess.run(
                ["reg", "query", path, "/v", "version"],
                capture_output=True, text=True, timeout=5
            )
            match = re.search(r"(\d+)\.\d+\.\d+\.\d+", result.stdout)
            if match:
                return int(match.group(1))
        except Exception:
            continue
    return None


class BrowserBot:
    """
    1つのChromeウィンドウを制御するボット。
    手動ログイン完了を検知してからスクロールループを実行する。
    """

    def __init__(
        self,
        index: int,
        target_url: str,
        scroll_interval: float,
        scroll_count: int,
        refresh_interval: float,
        log_callback: Callable[[str], None],
    ):
        """
        Args:
            index: インスタンス番号（1始まり）
            target_url: スクロール対象URL
            scroll_interval: PageDown間隔（秒）
            scroll_count: PageDown回数
            refresh_interval: F5更新までの時間（秒）
            log_callback: ログ出力コールバック関数
        """
        self.index = index
        self.target_url = target_url
        self.scroll_interval = scroll_interval
        self.scroll_count = scroll_count
        self.refresh_interval = refresh_interval
        self.log = log_callback
        self.driver: uc.Chrome | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        """インスタンス番号付きでログを出力する。"""
        self.log(f"インスタンス{self.index}: {message}")

    def _is_stopped(self) -> bool:
        """停止フラグが立っているか確認する。"""
        return self._stop_event.is_set()

    def _sleep(self, seconds: float) -> bool:
        """
        指定秒数スリープする。停止フラグが立ったら即座に抜ける。

        Returns:
            True: 正常にスリープ完了 / False: 停止フラグで中断
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
        undetected-chromedriver を使用してChromeを起動する。
        専用プロファイル・User-Agent・bot検知回避オプションを設定する。
        """
        profile_dir = os.path.join(PROFILES_DIR, f"account{self.index}")
        os.makedirs(profile_dir, exist_ok=True)

        options = uc.ChromeOptions()
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")

        chrome_version = _get_chrome_major_version()
        if chrome_version:
            self._log(f"Chrome バージョン検出: {chrome_version}")
        else:
            self._log("Chrome バージョンの自動検出に失敗しました。ucの自動検出を使用します。")

        driver = uc.Chrome(
            options=options,
            user_data_dir=profile_dir,
            version_main=chrome_version,
        )
        return driver

    # ------------------------------------------------------------------
    # ログイン状態の確認
    # ------------------------------------------------------------------

    def _is_on_home(self) -> bool:
        """
        現在のページがログイン済みホーム画面かを確認する。
        URLと認証済みナビバーDOMの両方で判定する。
        """
        try:
            url = self.driver.current_url
            if any(p in url for p in ("login", "i/flow", "signin")):
                return False
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, '[data-testid="AppTabBar_Home_Link"]'
            )
            return len(elements) > 0
        except WebDriverException:
            return False

    def _wait_for_manual_login(self) -> bool:
        """
        ユーザーが手動でログインするのを待機する（最大5分）。
        ホーム画面への遷移を検知したらTrueを返す。

        Returns:
            True: ログイン完了 / False: タイムアウトまたは停止
        """
        deadline = time.time() + MANUAL_AUTH_TIMEOUT
        while time.time() < deadline:
            if self._is_stopped():
                return False
            if self._is_on_home():
                self._log("✅ ログイン完了を確認しました")
                return True
            time.sleep(3)
        self._log("❌ ログイン待機タイムアウト（5分）")
        return False

    # ------------------------------------------------------------------
    # スクロールループ
    # ------------------------------------------------------------------

    def _press_page_down(self) -> None:
        """body要素を毎回取得してPageDownを1回押す。"""
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
        except WebDriverException:
            pass

    def _press_f5(self) -> None:
        """body要素を毎回取得してF5を押し、ページ読み込みを待機する。"""
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.F5)
            time.sleep(3)  # ページ読み込み待機
        except WebDriverException:
            pass

    def _scroll_loop(self) -> None:
        """
        以下を停止ボタンが押されるまで無限に繰り返す。

        ループ:
          1. PageDownを scroll_interval 秒ごとに scroll_count 回押す
          2. refresh_interval 秒待ってから F5 を押す
          3. 1 に戻る
        """
        self._log("スクロール動作を開始します")

        while not self._is_stopped():

            # Step 1: PageDownを scroll_interval 秒ごとに scroll_count 回押す
            for _ in range(self.scroll_count):
                if self._is_stopped():
                    return
                self._press_page_down()
                if not self._sleep(self.scroll_interval):
                    return

            # Step 2: refresh_interval 秒待つ
            if not self._sleep(self.refresh_interval):
                return

            # Step 3: F5更新
            if self._is_stopped():
                return
            self._log("🔄 F5更新")
            self._press_f5()

            # → Step 1 に戻る

    # ------------------------------------------------------------------
    # 公開インターフェース
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        ボットのメイン処理。以下の順で実行する。

        1. Chrome起動
        2. https://x.com/login に遷移
        3. 既存セッションがあれば /home を確認してスキップ
        4. 未ログインの場合は手動ログインを待機（最大5分）
        5. 対象URLへ遷移してスクロール動作を開始
        """
        self._stop_event.clear()
        try:
            self._log("Chromeを起動しています...")
            self.driver = self._build_driver()

            # ログインページへ遷移
            self._log("https://x.com/login に遷移します...")
            self.driver.get("https://x.com/login")
            time.sleep(3)

            # 既存セッション確認
            if self._is_on_home():
                self._log("✅ 既存セッションでログイン済み")
            else:
                # 手動ログイン待機
                self._log("⚠️ 手動でログインしてください。完了を自動検知します...")
                ok = self._wait_for_manual_login()
                if not ok:
                    return

            # 対象URLへ遷移
            self._log(f"対象URLへ遷移します: {self.target_url}")
            self.driver.get(self.target_url)
            time.sleep(3)

            # スクロールループ開始
            self._scroll_loop()

        except WebDriverException as e:
            self._log(f"❌ ブラウザエラー: {e}")
        except Exception as e:
            self._log(f"❌ 予期しないエラー: {e}")
        finally:
            self._quit()

    def stop(self) -> None:
        """ボットを停止する。スクロールループを抜けてChromeを閉じる。"""
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
