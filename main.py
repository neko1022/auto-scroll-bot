"""
自動スクロール＆更新ボット — メインGUIアプリ。

タブ構成:
  - 設定1〜5（固定）＋ 設定6〜10（ボタンで追加）
  - ログタブ（常に末尾）

フッター:
  - ▶ 開始: チェックボックスONのスロットのみ起動
  - ■ 停止: 全インスタンス一括停止
"""

import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from bot.manager import BotManager
from utils.storage import DEFAULT_SLOT, get_slot, load_settings, save_settings, save_slot

# ---- カラー定義 ---------------------------------------------------------------
C_PURPLE      = "#A020B8"
C_PURPLE_DEEP = "#7B0FA0"
C_PURPLE_DARK = "#6A0080"
C_PURPLE_PALE = "#E8D0F0"
C_CREAM       = "#F8F2FC"
C_TEXT_DARK   = "#2A0D38"
C_TEXT_MID    = "#6B3A82"
C_GOLD        = "#E6C77A"

# ログ色（スロット1〜10を5色でサイクル）
LOG_COLORS = ["#7B0FA0", "#1565C0", "#2E7D32", "#C84B00", "#AD1457"]

MAX_SLOTS    = 10
INIT_SLOTS   = 5


# ==============================================================================
# SettingsTab — 1スロット分の設定フォーム
# ==============================================================================

class SettingsTab(ttk.Frame):
    """
    スロット1件分の設定タブ。
    チェックボックス・URL・スクロール設定・メモ欄・保存ボタンを持つ。
    """

    def __init__(
        self,
        notebook: ttk.Notebook,
        slot: int,
        initial_data: dict,
        on_save: callable,
    ):
        """
        Args:
            notebook: 親のNotebookウィジェット
            slot: スロット番号（1〜10）
            initial_data: 保存済み設定辞書
            on_save: 保存ボタン押下時コールバック(slot, config)
        """
        super().__init__(notebook, style="Card.TFrame")
        self.slot = slot
        self._on_save = on_save

        # --- 変数 ---
        self.var_enabled  = tk.BooleanVar(value=initial_data.get("enabled", False))
        self.var_url      = tk.StringVar(value=initial_data.get("url", "https://"))
        self.var_interval = tk.DoubleVar(value=initial_data.get("scroll_interval", 3.0))
        self.var_count    = tk.IntVar(value=initial_data.get("scroll_count", 10))
        self.var_refresh  = tk.DoubleVar(value=initial_data.get("refresh_interval", 60.0))
        self.var_username = tk.StringVar(value=initial_data.get("username", ""))
        self.var_password = tk.StringVar(value=initial_data.get("password", ""))

        self._build()

        # チェックボックス変更時にタブラベルを更新
        self.var_enabled.trace_add("write", lambda *_: self._update_tab_label())

    # ------------------------------------------------------------------

    def _build(self) -> None:
        """フォームを構築する。"""
        self.columnconfigure(1, weight=1)
        pad = {"padx": (20, 12), "pady": 6}

        # --- 有効チェックボックス ---
        color = LOG_COLORS[(self.slot - 1) % len(LOG_COLORS)]
        cb = tk.Checkbutton(
            self,
            text=f"  スロット {self.slot} を有効にする",
            variable=self.var_enabled,
            bg=C_CREAM, fg=color,
            selectcolor=C_PURPLE_PALE,
            activebackground=C_CREAM,
            font=("Yu Gothic UI", 11, "bold"),
            cursor="hand2",
        )
        cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=20, pady=(14, 8))

        # --- 設定フィールド ---
        fields = [
            ("対象URL",              self.var_url,      "entry",   None, None, None),
            ("PageDown 間隔（秒）",  self.var_interval, "spinbox", 0.5,  60,   0.5),
            ("PageDown 回数",        self.var_count,    "spinbox", 1,    200,  1),
            ("F5更新までの時間（秒）",self.var_refresh,  "spinbox", 5,    7200, 5),
            ("ユーザー名（メモ）",   self.var_username, "entry",   None, None, None),
            ("パスワード（メモ）",   self.var_password, "entry",   None, None, None),
        ]

        for row, (label, var, ftype, from_, to, inc) in enumerate(fields, start=1):
            ttk.Label(self, text=label, style="Field.TLabel").grid(
                row=row, column=0, sticky=tk.W, **pad
            )
            if ftype == "entry":
                w = ttk.Entry(self, textvariable=var, style="Custom.TEntry")
            else:
                w = ttk.Spinbox(
                    self, from_=from_, to=to, increment=inc,
                    textvariable=var, style="Custom.TSpinbox", width=10,
                )
            w.grid(row=row, column=1, sticky=tk.EW, padx=(0, 20), pady=6)

        # --- 保存ボタン ---
        ttk.Button(
            self, text="設定を保存", style="Save.TButton",
            command=self._save,
        ).grid(row=len(fields) + 1, column=0, columnspan=2, pady=(10, 14))

    def _save(self) -> None:
        """設定を保存してコールバックを呼ぶ。"""
        self._on_save(self.slot, self.get_config())

    def _update_tab_label(self) -> None:
        """チェックボックスの状態をタブラベルに反映する。"""
        try:
            notebook = self.master
            idx = notebook.index(self)
            mark = " ✓" if self.var_enabled.get() else ""
            notebook.tab(idx, text=f" 設定{self.slot}{mark} ")
        except Exception:
            pass

    def get_config(self) -> dict:
        """現在の入力値を辞書で返す。"""
        return {
            "enabled":         self.var_enabled.get(),
            "url":             self.var_url.get().strip(),
            "scroll_interval": self.var_interval.get(),
            "scroll_count":    self.var_count.get(),
            "refresh_interval":self.var_refresh.get(),
            "username":        self.var_username.get(),
            "password":        self.var_password.get(),
        }


# ==============================================================================
# AutoScrollBotApp — メインアプリ
# ==============================================================================

class AutoScrollBotApp(tk.Tk):
    """自動スクロールボットのメインGUIウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("AutoScrollBot")
        self.geometry("680x590")
        self.minsize(640, 560)
        self.configure(bg=C_CREAM)

        self._settings_data   = load_settings()
        self._slot_tabs: list[SettingsTab] = []
        self._log_tab_frame: ttk.Frame | None = None
        self._manager         = BotManager()
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._setup_styles()
        self._build_header()
        self._build_toolbar()
        self._build_notebook()
        self._build_footer()
        self._poll_log_queue()

    # ------------------------------------------------------------------
    # スタイル
    # ------------------------------------------------------------------

    def _setup_styles(self) -> None:
        """ttk.Style でカスタムスタイルを定義する。"""
        s = ttk.Style(self)
        s.theme_use("clam")

        # Notebook
        s.configure("Custom.TNotebook",
                    background=C_CREAM, borderwidth=0)
        s.configure("Custom.TNotebook.Tab",
                    background=C_PURPLE_PALE, foreground=C_TEXT_DARK,
                    padding=(10, 5), font=("Yu Gothic UI", 9, "bold"))
        s.map("Custom.TNotebook.Tab",
              background=[("selected", C_PURPLE), ("active", C_PURPLE_DEEP)],
              foreground=[("selected", "white"), ("active", "white")])

        # Frame
        s.configure("Card.TFrame", background=C_CREAM)

        # Label
        s.configure("Title.TLabel",
                    background=C_CREAM, foreground=C_TEXT_DARK,
                    font=("Yu Gothic UI", 11, "bold"))
        s.configure("Field.TLabel",
                    background=C_CREAM, foreground=C_TEXT_MID,
                    font=("Yu Gothic UI", 10))

        # Entry / Spinbox
        s.configure("Custom.TEntry",
                    fieldbackground="white", foreground=C_TEXT_DARK,
                    bordercolor=C_PURPLE_PALE, insertcolor=C_TEXT_DARK)
        s.configure("Custom.TSpinbox",
                    fieldbackground="white", foreground=C_TEXT_DARK)

        # Buttons
        s.configure("Start.TButton",
                    background=C_PURPLE, foreground="white",
                    font=("Yu Gothic UI", 11, "bold"),
                    padding=(22, 8), borderwidth=0, relief="flat")
        s.map("Start.TButton",
              background=[("active", C_PURPLE_DEEP), ("disabled", "#C0A0CC")])

        s.configure("Stop.TButton",
                    background=C_PURPLE_DARK, foreground="white",
                    font=("Yu Gothic UI", 11, "bold"),
                    padding=(22, 8), borderwidth=0, relief="flat")
        s.map("Stop.TButton",
              background=[("active", "#4A005A"), ("disabled", "#A090A8")])

        s.configure("Save.TButton",
                    background=C_GOLD, foreground=C_TEXT_DARK,
                    font=("Yu Gothic UI", 10, "bold"),
                    padding=(18, 6), borderwidth=0, relief="flat")
        s.map("Save.TButton", background=[("active", "#C9A84C")])

        s.configure("Add.TButton",
                    background=C_PURPLE_PALE, foreground=C_PURPLE_DARK,
                    font=("Yu Gothic UI", 10, "bold"),
                    padding=(12, 4), borderwidth=0, relief="flat")
        s.map("Add.TButton",
              background=[("active", C_PURPLE_PALE), ("disabled", "#E0D8E8")])

    # ------------------------------------------------------------------
    # ヘッダー
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        """タイトルバーを構築する。"""
        h = tk.Frame(self, bg=C_PURPLE_DARK, height=44)
        h.pack(fill=tk.X)
        h.pack_propagate(False)
        tk.Label(h, text="✦  AutoScrollBot  ✦",
                 bg=C_PURPLE_DARK, fg=C_GOLD,
                 font=("Yu Gothic UI", 13, "bold")).pack(expand=True)

    # ------------------------------------------------------------------
    # ツールバー（タブ追加ボタン）
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        """タブ追加ボタンを持つツールバーを構築する。"""
        bar = tk.Frame(self, bg=C_CREAM, height=36)
        bar.pack(fill=tk.X, padx=10, pady=(4, 0))
        bar.pack_propagate(False)

        self._btn_add_tab = ttk.Button(
            bar, text=self._add_btn_label(),
            style="Add.TButton",
            command=self._on_add_tab,
        )
        self._btn_add_tab.pack(side=tk.LEFT, padx=2, pady=4)

        if len(self._slot_tabs) >= MAX_SLOTS:
            self._btn_add_tab.config(state=tk.DISABLED)

    def _add_btn_label(self) -> str:
        """タブ追加ボタンのラベルを生成する。"""
        count = len(self._slot_tabs)
        return f"  ＋ タブを追加  ({count}/{MAX_SLOTS})"

    def _refresh_add_btn(self) -> None:
        """タブ追加ボタンのラベルと有効状態を更新する。"""
        count = len(self._slot_tabs)
        self._btn_add_tab.config(text=self._add_btn_label())
        state = tk.DISABLED if count >= MAX_SLOTS else tk.NORMAL
        self._btn_add_tab.config(state=state)

    # ------------------------------------------------------------------
    # ノートブック
    # ------------------------------------------------------------------

    def _build_notebook(self) -> None:
        """設定タブ（保存済み数）とログタブを構築する。"""
        self._notebook = ttk.Notebook(self, style="Custom.TNotebook")
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 4))

        slot_count = max(INIT_SLOTS, self._settings_data.get("slot_count", INIT_SLOTS))
        slot_count = min(slot_count, MAX_SLOTS)

        for i in range(1, slot_count + 1):
            self._create_settings_tab(i)

        self._create_log_tab()
        self._refresh_add_btn()

    def _create_settings_tab(self, slot: int) -> None:
        """設定タブを1件作成してノートブックに追加する。"""
        data = get_slot(self._settings_data, slot)
        tab = SettingsTab(self._notebook, slot, data, self._on_save_slot)
        self._slot_tabs.append(tab)

        mark = " ✓" if data.get("enabled") else ""
        label = f" 設定{slot}{mark} "

        if self._log_tab_frame is not None:
            # ログタブの直前に挿入
            log_idx = self._notebook.index(self._log_tab_frame)
            self._notebook.insert(log_idx, tab, text=label)
        else:
            self._notebook.add(tab, text=label)

    def _create_log_tab(self) -> None:
        """ログタブを末尾に追加する。"""
        self._log_tab_frame = ttk.Frame(self._notebook, style="Card.TFrame")
        self._notebook.add(self._log_tab_frame, text=" ログ ")
        self._build_log_area(self._log_tab_frame)

    # ------------------------------------------------------------------
    # ログエリア
    # ------------------------------------------------------------------

    def _build_log_area(self, parent: ttk.Frame) -> None:
        """ログタブの内側にテキストエリアを構築する。"""
        self._log_text = tk.Text(
            parent,
            bg="#1C0A2A", fg=C_PURPLE_PALE,
            font=("Consolas", 9),
            wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT, padx=8, pady=6,
        )
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # スロットごとの色タグを登録
        for i in range(1, MAX_SLOTS + 1):
            color = LOG_COLORS[(i - 1) % len(LOG_COLORS)]
            self._log_text.tag_configure(f"slot{i}", foreground=color)
        self._log_text.tag_configure("system", foreground=C_GOLD)

    # ------------------------------------------------------------------
    # フッター
    # ------------------------------------------------------------------

    def _build_footer(self) -> None:
        """開始・停止ボタンを持つフッターを構築する。"""
        footer = tk.Frame(self, bg=C_PURPLE_PALE, height=56)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)

        inner = tk.Frame(footer, bg=C_PURPLE_PALE)
        inner.pack(expand=True)

        self._btn_start = ttk.Button(
            inner, text="▶  開始", style="Start.TButton",
            command=self._on_start,
        )
        self._btn_start.pack(side=tk.LEFT, padx=10, pady=8)

        self._btn_stop = ttk.Button(
            inner, text="■  停止", style="Stop.TButton",
            command=self._on_stop, state=tk.DISABLED,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=10, pady=8)

    # ------------------------------------------------------------------
    # イベントハンドラ
    # ------------------------------------------------------------------

    def _on_add_tab(self) -> None:
        """タブ追加ボタン: 次のスロット番号の設定タブを追加する。"""
        if len(self._slot_tabs) >= MAX_SLOTS:
            return

        slot = len(self._slot_tabs) + 1
        self._create_settings_tab(slot)

        # slot_count を更新して保存
        self._settings_data["slot_count"] = len(self._slot_tabs)
        save_settings(self._settings_data)

        # 新しいタブにフォーカス
        self._notebook.select(self._slot_tabs[-1])
        self._refresh_add_btn()

    def _on_save_slot(self, slot: int, config: dict) -> None:
        """設定タブの「設定を保存」ボタン: 当該スロットを保存する。"""
        save_slot(slot, config)
        messagebox.showinfo("保存完了", f"設定{slot} を保存しました。")

    def _on_start(self) -> None:
        """開始ボタン: 有効スロットを収集してBotManagerを起動する。"""
        enabled = []
        for tab in self._slot_tabs:
            cfg = tab.get_config()
            if not cfg["enabled"]:
                continue
            if not cfg["url"].startswith("https://"):
                messagebox.showwarning(
                    "入力エラー",
                    f"設定{tab.slot}: URLは https:// から始める必要があります。"
                )
                return
            enabled.append({"slot": tab.slot, **cfg})

        if not enabled:
            messagebox.showwarning(
                "設定エラー",
                "有効なスロットが1つもありません。\n"
                "いずれかの設定タブでチェックボックスをONにしてください。"
            )
            return

        self._btn_start.config(state=tk.DISABLED)
        self._btn_stop.config(state=tk.NORMAL)
        self._notebook.select(self._log_tab_frame)

        self._manager.start(enabled, self._enqueue_log)
        threading.Thread(target=self._watch_bots, daemon=True).start()

    def _on_stop(self) -> None:
        """停止ボタン: 全ボットに停止シグナルを送る。"""
        self._manager.stop()
        self._btn_stop.config(state=tk.DISABLED)

    def _watch_bots(self) -> None:
        """全スレッド終了を監視して開始ボタンを復活させる。"""
        import time
        while self._manager.is_running():
            time.sleep(1)
        self.after(0, lambda: self._btn_start.config(state=tk.NORMAL))
        self.after(0, lambda: self._btn_stop.config(state=tk.DISABLED))

    # ------------------------------------------------------------------
    # ログ処理
    # ------------------------------------------------------------------

    def _enqueue_log(self, message: str) -> None:
        """スレッドから安全にログをキューに追加する。"""
        tag = "system"
        for i in range(1, MAX_SLOTS + 1):
            if f"スロット{i}:" in message:
                tag = f"slot{i}"
                break
        self._log_queue.put((message, tag))

    def _poll_log_queue(self) -> None:
        """100msごとにキューを確認してログを描画する。"""
        try:
            while True:
                message, tag = self._log_queue.get_nowait()
                self._append_log(message, tag)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _append_log(self, message: str, tag: str = "system") -> None:
        """ログテキストエリアにタイムスタンプ付きでメッセージを追記する。"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{ts}] {message}\n", tag)
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)


# ---- エントリポイント -----------------------------------------------------------

if __name__ == "__main__":
    app = AutoScrollBotApp()
    app.mainloop()
