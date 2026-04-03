"""
単一Chromeインスタンスのログイン・スクロール・F5更新を担うクラス。
各インスタンスは専用Chromeプロファイルを使用し、スレッド内で独立して動作する。
"""

import os
import time
import threading
from typing import Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

# プロファイル保存先
_BASE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
PROFILES_DIR = os.path.join(_BASE_DIR, "profiles")

# 手動認証待機の最大秒数
MANUAL_AUTH_TIMEOUT = 300  # 5分


class BrowserBot:
    """
    1つのChromeウィンドウを制御するボット。
    ログイン判定・自動ログイン・スクロールループを担う。
    """

    def __init__(
        self,
        index: int,
        username: str,
        password: str,
        target_url: str,
        scroll_interval: float,
        scroll_count: int,
        refresh_interval: float,
        log_callback: Callable[[str], None],
    ):
        """
        Args:
            index: インスタンス番号（1始まり）
            username: Twitterユーザー名
            password: Twitterパスワード
            target_url: スクロール対象URL
            scroll_interval: PageDown間隔（秒）
            scroll_count: PageDown回数
            refresh_interval: F5更新までの時間（秒）
            log_callback: ログ出力コールバック関数
        """
        self.index = index
        self.username = username
        self.password = password
        self.target_url = target_url
        self.scroll_interval = scroll_interval
        self.scroll_count = scroll_count
        self.refresh_interval = refresh_interval
        self.log = log_callback
        self.driver: webdriver.Chrome | None = None
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

    def _build_driver(self) -> webdriver.Chrome:
        """専用プロファイルを使用したChromeドライバを生成して返す。"""
        profile_dir = os.path.join(PROFILES_DIR, f"account{self.index}")
        os.makedirs(profile_dir, exist_ok=True)

        options = Options()
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        # Selenium検知回避
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver

    # ------------------------------------------------------------------
    # ログイン判定・ログイン処理
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """
        現在のページがTwitterのホーム画面かどうかを判定する。
        URLに /home が含まれるか、またはセッションCookieが存在するかで判定。
        """
        try:
            url = self.driver.current_url
            # ホーム・タイムライン・検索ページ等ならログイン済みとみなす
            logged_in_patterns = ["/home", "/i/", "/search", "twitter.com/", "x.com/"]
            login_page_patterns = ["twitter.com/login", "x.com/login",
                                   "twitter.com/i/flow/login", "x.com/i/flow/login"]
            if any(p in url for p in login_page_patterns):
                return False
            if any(p in url for p in logged_in_patterns):
                return True
            # Cookieによる判定
            cookies = self.driver.get_cookies()
            auth_cookies = [c for c in cookies if c.get("name") in ("auth_token", "ct0")]
            return len(auth_cookies) > 0
        except WebDriverException:
            return False

    def _wait_for_element(self, by: str, value: str, timeout: int = 15):
        """指定要素が現れるまで待機して返す。見つからなければNoneを返す。"""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except TimeoutException:
            return None

    def _login(self) -> bool:
        """
        Twitterへ自動ログインを試みる。

        Returns:
            True: ログイン成功 / False: ログイン失敗
        """
        self._log("ログインページに遷移します...")
        try:
            self.driver.get("https://x.com/i/flow/login")
            time.sleep(2)

            # ユーザー名入力
            username_input = self._wait_for_element(
                By.CSS_SELECTOR, 'input[autocomplete="username"]', timeout=20
            )
            if not username_input:
                self._log("❌ ユーザー名入力欄が見つかりませんでした")
                return False
            username_input.clear()
            username_input.send_keys(self.username)
            username_input.send_keys(Keys.RETURN)
            time.sleep(2)

            # 追加確認（電話番号・メールアドレス要求）
            try:
                extra_input = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')
                    )
                )
                self._log("⚠️ 追加認証（電話番号/メール）を求められました。手動で入力してください。")
                extra_input.send_keys(self.username)
                extra_input.send_keys(Keys.RETURN)
                time.sleep(2)
            except TimeoutException:
                pass  # 追加確認なし

            # パスワード入力
            password_input = self._wait_for_element(
                By.CSS_SELECTOR, 'input[type="password"]', timeout=15
            )
            if not password_input:
                self._log("❌ パスワード入力欄が見つかりませんでした")
                return False
            password_input.clear()
            password_input.send_keys(self.password)
            password_input.send_keys(Keys.RETURN)
            time.sleep(3)

            # 2段階認証・メール確認などの追加フロー検知
            current_url = self.driver.current_url
            is_challenge = any(
                p in current_url
                for p in ["challenge", "confirm", "verify", "2fa", "account/login"]
            )
            if is_challenge or not self._is_logged_in():
                self._log("⚠️ 手動認証をお待ちしています...")
                return self._wait_for_manual_auth()

            if self._is_logged_in():
                self._log("✅ ログイン完了")
                return True
            else:
                self._log("❌ ログイン失敗")
                return False

        except WebDriverException as e:
            self._log(f"❌ ログイン中にエラーが発生しました: {e}")
            return False

    def _wait_for_manual_auth(self) -> bool:
        """
        手動認証が完了するまでポーリングで待機する（最大5分）。

        Returns:
            True: ログイン確認 / False: タイムアウト
        """
        deadline = time.time() + MANUAL_AUTH_TIMEOUT
        while time.time() < deadline:
            if self._is_stopped():
                return False
            if self._is_logged_in():
                self._log("✅ 手動認証完了・ログイン確認")
                return True
            time.sleep(5)
        self._log("❌ 手動認証タイムアウト（5分）")
        return False

    # ------------------------------------------------------------------
    # スクロールループ
    # ------------------------------------------------------------------

    def _scroll_loop(self) -> None:
        """
        スクロール＆F5更新を停止フラグが立つまでループ実行する。
        """
        self._log("スクロール動作を開始します")
        body = None

        while not self._is_stopped():
            # body要素の取得（ページ遷移後に再取得が必要な場合がある）
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
            except WebDriverException:
                self._log("⚠️ ページ要素の取得に失敗しました。リトライします...")
                if not self._sleep(2):
                    break
                continue

            # PageDownをscroll_count回実行
            for i in range(self.scroll_count):
                if self._is_stopped():
                    return
                try:
                    body.send_keys(Keys.PAGE_DOWN)
                except WebDriverException:
                    pass
                if not self._sleep(self.scroll_interval):
                    return

            # F5更新までの待機
            if not self._sleep(self.refresh_interval):
                return

            # F5更新
            if self._is_stopped():
                return
            try:
                self._log("🔄 F5更新")
                body.send_keys(Keys.F5)
                time.sleep(3)  # ページ読み込み待機
            except WebDriverException:
                pass

    # ------------------------------------------------------------------
    # 公開インターフェース
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        ボットのメイン処理。
        Chrome起動 → ログイン → スクロールループ の順に実行する。
        """
        self._stop_event.clear()
        try:
            self._log("Chromeを起動しています...")
            self.driver = self._build_driver()

            # ターゲットURLを開く
            self.driver.get(self.target_url)
            time.sleep(3)

            # ログイン確認
            if not self._is_logged_in():
                success = self._login()
                if not success:
                    return
                # ログイン後に対象URLへ遷移
                self.driver.get(self.target_url)
                time.sleep(3)
            else:
                self._log("✅ 既存セッションでログイン済み")

            # スクロールループ
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
