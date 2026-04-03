"""
自動スクロール＆更新ボット - エントリポイント・GUIアプリ。
tkinterで3タブ構成のGUIを構築する。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
from datetime import datetime

from utils.storage import load_settings, save_settings, load_accounts, save_accounts
from bot.manager import BotManager

# ---- カラー定義 ----------------------------------------------------------------
C_PURPLE      = "#A020B8"
C_PURPLE_DEEP = "#7B0FA0"
C_PURPLE_DARK = "#6A0080"
C_PURPLE_PALE = "#E8D0F0"
C_CREAM       = "#F8F2FC"
C_TEXT_DARK   = "#2A0D38"
C_TEXT_MID    = "#6B3A82"
C_GOLD        = "#E6C77A"

# インスタンスごとのログ色
INSTANCE_COLORS = [
    "#7B0FA0",  # 1: purple-deep
    "#1565C0",  # 2: blue
    "#2E7D32",  # 3: green
    "#E65100",  # 4: orange
    "#AD1457",  # 5: pink
]


class AutoScrollBotApp(tk.Tk):
    """
    自動スクロールボットのメインGUIアプリケーション。
    3タブ（基本設定・アカウント設定・ログ）と共通フッターで構成される。
    """

    def __init__(self):
        super().__init__()
        self.title("AutoScrollBot")
        self.geometry("640x560")
        self.resizable(False, False)
        self.configure(bg=C_CREAM)

        # ログキュー（スレッドセーフな受け渡し）
        self._log_queue: queue.Queue[tuple[str, int]] = queue.Queue()

        # ボット管理
        self._manager = BotManager(log_callback=self._enqueue_log)

        # 設定・アカウント読み込み
        self._settings = load_settings()
        self._accounts = load_accounts()

        # GUIの構築
        self._setup_styles()
        self._build_header()
        self._build_tabs()
        self._build_footer()

        # タブ2のアカウントフォームを初期化
        self._refresh_account_forms()

        # ログのポーリング開始
        self._poll_log_queue()

    # ------------------------------------------------------------------
    # スタイル設定
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        """ttk.Style でカスタムスタイルを定義する。"""
        style = ttk.Style(self)
        style.theme_use("clam")

        # ノートブック（タブ）
        style.configure(
            "Custom.TNotebook",
            background=C_CREAM,
            borderwidth=0,
        )
        style.configure(
            "Custom.TNotebook.Tab",
            background=C_PURPLE_PALE,
            foreground=C_TEXT_DARK,
            padding=(14, 6),
            font=("Yu Gothic UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Custom.TNotebook.Tab",
            background=[("selected", C_PURPLE), ("active", C_PURPLE_DEEP)],
            foreground=[("selected", "white"), ("active", "white")],
        )

        # フレーム
        style.configure("Card.TFrame", background=C_CREAM)

        # ラベル
        style.configure(
            "Title.TLabel",
            background=C_CREAM,
            foreground=C_TEXT_DARK,
            font=("Yu Gothic UI", 11, "bold"),
        )
        style.configure(
            "Field.TLabel",
            background=C_CREAM,
            foreground=C_TEXT_MID,
            font=("Yu Gothic UI", 10),
        )

        # エントリ
        style.configure(
            "Custom.TEntry",
            fieldbackground="white",
            foreground=C_TEXT_DARK,
            bordercolor=C_PURPLE_PALE,
            insertcolor=C_TEXT_DARK,
        )

        # スピンボックス
        style.configure(
            "Custom.TSpinbox",
            fieldbackground="white",
            foreground=C_TEXT_DARK,
        )

        # ボタン
        style.configure(
            "Start.TButton",
            background=C_PURPLE,
            foreground="white",
            font=("Yu Gothic UI", 11, "bold"),
            padding=(20, 8),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Start.TButton",
            background=[("active", C_PURPLE_DEEP)],
        )
        style.configure(
            "Stop.TButton",
            background=C_PURPLE_DARK,
            foreground="white",
            font=("Yu Gothic UI", 11, "bold"),
            padding=(20, 8),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Stop.TButton",
            background=[("active", "#4A005A")],
        )
        style.configure(
            "Save.TButton",
            background=C_GOLD,
            foreground=C_TEXT_DARK,
            font=("Yu Gothic UI", 10, "bold"),
            padding=(16, 6),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Save.TButton",
            background=[("active", "#D4A850")],
        )

    # ------------------------------------------------------------------
    # ヘッダー
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        """アプリ上部のタイトルバーを構築する。"""
        header = tk.Frame(self, bg=C_PURPLE_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="✦  AutoScrollBot  ✦",
            bg=C_PURPLE_DARK,
            fg=C_GOLD,
            font=("Yu Gothic UI", 14, "bold"),
        ).pack(expand=True)

    # ------------------------------------------------------------------
    # タブ構築
    # ------------------------------------------------------------------

    def _build_tabs(self) -> None:
        """3タブ（基本設定・アカウント設定・ログ）のノートブックを構築する。"""
        self._notebook = ttk.Notebook(self, style="Custom.TNotebook")
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))

        # タブ1
        tab1 = ttk.Frame(self._notebook, style="Card.TFrame")
        self._notebook.add(tab1, text="  基本設定  ")
        self._build_tab_settings(tab1)

        # タブ2
        tab2 = ttk.Frame(self._notebook, style="Card.TFrame")
        self._notebook.add(tab2, text="  アカウント設定  ")
        self._build_tab_accounts(tab2)

        # タブ3
        tab3 = ttk.Frame(self._notebook, style="Card.TFrame")
        self._notebook.add(tab3, text="  ログ  ")
        self._build_tab_log(tab3)

    # ------------------------------------------------------------------
    # タブ1: 基本設定
    # ------------------------------------------------------------------

    def _build_tab_settings(self, parent: ttk.Frame) -> None:
        """基本設定タブのウィジェットを構築する。"""
        pad = {"padx": 20, "pady": 6}
        parent.columnconfigure(1, weight=1)

        def row(r: int, label: str, widget_factory):
            ttk.Label(parent, text=label, style="Field.TLabel").grid(
                row=r, column=0, sticky=tk.W, **pad
            )
            w = widget_factory(parent)
            w.grid(row=r, column=1, sticky=tk.EW, padx=(0, 20), pady=6)
            return w

        # 対象URL
        self._var_url = tk.StringVar(value=self._settings.get("url", "https://"))
        row(0, "対象URL", lambda p: ttk.Entry(p, textvariable=self._var_url, style="Custom.TEntry"))

        # PageDown間隔
        self._var_interval = tk.DoubleVar(value=self._settings.get("scroll_interval", 3))
        row(1, "PageDown間隔（秒）",
            lambda p: ttk.Spinbox(p, from_=0.5, to=60, increment=0.5,
                                  textvariable=self._var_interval,
                                  style="Custom.TSpinbox", width=10))

        # PageDown回数
        self._var_count = tk.IntVar(value=self._settings.get("scroll_count", 5))
        row(2, "PageDown回数",
            lambda p: ttk.Spinbox(p, from_=1, to=100, increment=1,
                                  textvariable=self._var_count,
                                  style="Custom.TSpinbox", width=10))

        # F5更新までの時間
        self._var_refresh = tk.DoubleVar(value=self._settings.get("refresh_interval", 60))
        row(3, "F5更新までの時間（秒）",
            lambda p: ttk.Spinbox(p, from_=5, to=3600, increment=5,
                                  textvariable=self._var_refresh,
                                  style="Custom.TSpinbox", width=10))

        # インスタンス数
        self._var_instances = tk.IntVar(value=self._settings.get("instance_count", 1))
        spin = ttk.Spinbox(
            parent, from_=1, to=5, increment=1,
            textvariable=self._var_instances,
            style="Custom.TSpinbox", width=10,
            command=self._refresh_account_forms,
        )
        ttk.Label(parent, text="起動インスタンス数（1〜5）", style="Field.TLabel").grid(
            row=4, column=0, sticky=tk.W, **pad
        )
        spin.grid(row=4, column=1, sticky=tk.W, padx=(0, 20), pady=6)

        # 保存ボタン
        ttk.Button(
            parent, text="設定を保存", style="Save.TButton",
            command=self._save_settings,
        ).grid(row=5, column=0, columnspan=2, pady=(16, 4))

    def _save_settings(self) -> None:
        """基本設定をsettings.jsonに保存する。"""
        url = self._var_url.get().strip()
        if not url.startswith("https://"):
            messagebox.showwarning("入力エラー", "URLはhttps://から始める必要があります。")
            return
        settings = {
            "url": url,
            "scroll_interval": self._var_interval.get(),
            "scroll_count": self._var_count.get(),
            "refresh_interval": self._var_refresh.get(),
            "instance_count": self._var_instances.get(),
        }
        save_settings(settings)
        self._settings = settings
        self._refresh_account_forms()
        messagebox.showinfo("保存完了", "基本設定を保存しました。")

    # ------------------------------------------------------------------
    # タブ2: アカウント設定
    # ------------------------------------------------------------------

    def _build_tab_accounts(self, parent: ttk.Frame) -> None:
        """アカウント設定タブのスクロール可能なコンテナを構築する。"""
        self._accounts_tab_parent = parent

        # スクロール可能フレーム
        canvas = tk.Canvas(parent, bg=C_CREAM, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._accounts_inner = ttk.Frame(canvas, style="Card.TFrame")
        self._accounts_inner_id = canvas.create_window(
            (0, 0), window=self._accounts_inner, anchor=tk.NW
        )

        self._accounts_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self._accounts_inner_id, width=e.width),
        )

        # アカウントフォーム変数のリスト（最大5）
        self._account_vars: list[tuple[tk.StringVar, tk.StringVar]] = [
            (tk.StringVar(), tk.StringVar()) for _ in range(5)
        ]

        # 既存アカウントデータを変数にセット
        for i, acc in enumerate(self._accounts):
            if i < 5:
                self._account_vars[i][0].set(acc.get("username", ""))
                self._account_vars[i][1].set(acc.get("password", ""))

        self._account_form_canvas = canvas

    def _refresh_account_forms(self) -> None:
        """インスタンス数に合わせてアカウントフォームを再描画する。"""
        if not hasattr(self, "_accounts_inner"):
            return

        # 既存ウィジェットをクリア
        for w in self._accounts_inner.winfo_children():
            w.destroy()

        count = self._var_instances.get()

        for i in range(count):
            color = INSTANCE_COLORS[i % len(INSTANCE_COLORS)]
            frame = tk.LabelFrame(
                self._accounts_inner,
                text=f"  インスタンス {i + 1}  ",
                bg=C_CREAM,
                fg=color,
                font=("Yu Gothic UI", 10, "bold"),
                bd=1,
                relief=tk.GROOVE,
            )
            frame.pack(fill=tk.X, padx=16, pady=(8, 4))
            frame.columnconfigure(1, weight=1)

            # ユーザー名
            tk.Label(frame, text="ユーザー名", bg=C_CREAM, fg=C_TEXT_MID,
                     font=("Yu Gothic UI", 10)).grid(
                row=0, column=0, sticky=tk.W, padx=12, pady=6
            )
            ttk.Entry(frame, textvariable=self._account_vars[i][0],
                      style="Custom.TEntry").grid(
                row=0, column=1, sticky=tk.EW, padx=(0, 12), pady=6
            )

            # パスワード
            tk.Label(frame, text="パスワード", bg=C_CREAM, fg=C_TEXT_MID,
                     font=("Yu Gothic UI", 10)).grid(
                row=1, column=0, sticky=tk.W, padx=12, pady=6
            )
            ttk.Entry(frame, textvariable=self._account_vars[i][1],
                      show="●", style="Custom.TEntry").grid(
                row=1, column=1, sticky=tk.EW, padx=(0, 12), pady=6
            )

        # 保存ボタン
        ttk.Button(
            self._accounts_inner,
            text="アカウント情報を保存",
            style="Save.TButton",
            command=self._save_accounts,
        ).pack(pady=14)

    def _save_accounts(self) -> None:
        """アカウント情報をFernet暗号化してaccounts.jsonに保存する。"""
        count = self._var_instances.get()
        accounts = []
        for i in range(count):
            username = self._account_vars[i][0].get().strip()
            password = self._account_vars[i][1].get()
            accounts.append({"username": username, "password": password})
        save_accounts(accounts)
        self._accounts = accounts
        messagebox.showinfo("保存完了", "アカウント情報を暗号化して保存しました。")

    # ------------------------------------------------------------------
    # タブ3: ログ
    # ------------------------------------------------------------------

    def _build_tab_log(self, parent: ttk.Frame) -> None:
        """ログタブのテキストエリアを構築する。"""
        self._log_text = tk.Text(
            parent,
            bg="#1C0A2A",
            fg=C_PURPLE_PALE,
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # インスタンスごとの色タグを登録
        for i, color in enumerate(INSTANCE_COLORS, start=1):
            self._log_text.tag_configure(f"inst{i}", foreground=color)
        self._log_text.tag_configure("system", foreground=C_GOLD)
        self._log_text.tag_configure("default", foreground=C_PURPLE_PALE)

    # ------------------------------------------------------------------
    # フッター（開始・停止ボタン）
    # ------------------------------------------------------------------

    def _build_footer(self) -> None:
        """共通フッターの開始・停止ボタンを構築する。"""
        footer = tk.Frame(self, bg=C_PURPLE_PALE, height=56)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)

        # 左右にグルーを置いてボタンを中央揃えにする
        inner = tk.Frame(footer, bg=C_PURPLE_PALE)
        inner.pack(expand=True)

        self._btn_start = ttk.Button(
            inner, text="▶  開始", style="Start.TButton",
            command=self._on_start,
        )
        self._btn_start.pack(side=tk.LEFT, padx=10, pady=8)

        self._btn_stop = ttk.Button(
            inner, text="■  停止", style="Stop.TButton",
            command=self._on_stop,
            state=tk.DISABLED,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=10, pady=8)

    # ------------------------------------------------------------------
    # 開始・停止ハンドラ
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        """開始ボタン押下時の処理。バリデーションを行い全インスタンスを起動する。"""
        url = self._var_url.get().strip()
        if not url.startswith("https://"):
            messagebox.showwarning("入力エラー", "URLはhttps://から始める必要があります。")
            return

        count = self._var_instances.get()
        accounts = self._accounts[:count]

        # アカウント数が足りなければUI上の値を使う
        if len(accounts) < count:
            accounts = []
            for i in range(count):
                username = self._account_vars[i][0].get().strip()
                password = self._account_vars[i][1].get()
                accounts.append({"username": username, "password": password})

        if not any(a["username"] for a in accounts):
            messagebox.showwarning("入力エラー", "少なくとも1つのアカウントを設定してください。")
            return

        self._btn_start.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)

        # ログタブに切り替え
        self._notebook.select(2)

        self._manager.start(
            accounts=accounts,
            target_url=url,
            scroll_interval=self._var_interval.get(),
            scroll_count=self._var_count.get(),
            refresh_interval=self._var_refresh.get(),
        )

        # ボットが全停止したら開始ボタンを復活させる監視スレッド
        threading.Thread(target=self._watch_bots, daemon=True).start()

    def _on_stop(self) -> None:
        """停止ボタン押下時の処理。全インスタンスに停止シグナルを送る。"""
        self._manager.stop()
        self._btn_stop.config(state=tk.DISABLED)

    def _watch_bots(self) -> None:
        """全ボットスレッドの終了を監視し、終了後に開始ボタンを有効化する。"""
        import time
        while self._manager.is_running():
            time.sleep(1)
        # GUIスレッドに戻して状態更新
        self.after(0, lambda: self._btn_start.config(state=tk.NORMAL))
        self.after(0, lambda: self._btn_stop.config(state=tk.DISABLED))

    # ------------------------------------------------------------------
    # ログ処理
    # ------------------------------------------------------------------

    def _enqueue_log(self, message: str) -> None:
        """
        スレッドから安全にログをキューに追加する。
        メッセージからインスタンス番号を解析して色タグを決定する。
        """
        # インスタンス番号を解析
        tag = "system"
        for i in range(1, 6):
            if f"インスタンス{i}" in message:
                tag = f"inst{i}"
                break
        self._log_queue.put((message, tag))

    def _poll_log_queue(self) -> None:
        """メインスレッドでキューを定期的に確認してログを描画する。"""
        try:
            while True:
                message, tag = self._log_queue.get_nowait()
                self._append_log(message, tag)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, message: str, tag: str = "default") -> None:
        """ログテキストエリアにメッセージを追記する。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, line, tag)
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)


# ---- エントリポイント ----------------------------------------------------------

if __name__ == "__main__":
    app = AutoScrollBotApp()
    app.mainloop()
