# 自動スクロール＆更新ボット

## プロジェクト概要
指定URLを複数のブラウザウィンドウで自動操作するデスクトップGUIアプリ。
インスタンスごとに別Twitterアカウントでログインし、最大5つのChromeを同時並列で動かす。
PyInstallerでexe化して配布。相手はexeをダブルクリックするだけで使える。

## 技術スタック
- Python 3.10+
- GUI: tkinter（標準ライブラリ）
- ブラウザ自動操作: selenium + webdriver-manager
- 並列処理: threading
- 暗号化: cryptography（Fernet）
- 設定保存: accounts.json（Fernet暗号化）、settings.json（平文）
- exe化: PyInstaller

## ファイル構成
```
/
├── CLAUDE.md
├── README.md
├── requirements.txt        # selenium, webdriver-manager, cryptography, pyinstaller
├── main.py                 # エントリポイント・GUIアプリ
├── bot/
│   ├── __init__.py
│   ├── browser_bot.py      # 単一インスタンス（ログイン・スクロール・更新）
│   └── manager.py          # 複数インスタンスの並列管理
└── utils/
    ├── __init__.py
    ├── crypto.py           # Fernet暗号化・復号
    └── storage.py          # accounts.json / settings.json の読み書き
```

## プロファイル管理
- 各インスタンスに専用Chromeプロファイルを割り当てる
- プロファイルは `profiles/account{n}/` に保存（セッション・Cookie保持）
- 2回目以降の起動はプロファイルを再利用し、ログインをスキップ

```
profiles/
├── account1/   ← インスタンス1専用
├── account2/
├── account3/
├── account4/
└── account5/
```

## ログインフロー（browser_bot.py）
```
1. Chromeをプロファイル付きで起動
2. 対象URLを開く
3. ログイン済みか判定（セッションCookieの有無）
4. 未ログインの場合:
   a. twitter.com/login に遷移
   b. ユーザー名・パスワードを自動入力
   c. ログインボタンをクリック
   d. 承認要求（2段階認証・メール確認など）を検知した場合:
      - ブラウザをそのまま表示したまま待機
      - GUIログに「⚠️ インスタンスN: 手動認証をお待ちしています...」と表示
      - ログイン完了（ホーム画面に遷移）を最大5分間ポーリングで検知
      - 完了後に自動でスクロール動作を開始
5. ログイン完了後、対象URLに遷移してスクロール動作を開始
```

## スクロール動作フロー
```
ループ:
  1. PageDownキーを「間隔（秒）」ごとに「回数」分押す
  2. 「F5更新までの時間（秒）」経過後にF5を押す
  3. 1に戻る（停止ボタンが押されるまで繰り返す）
```

## GUI構成（タブ or スクロール画面）

### タブ1: 基本設定
- 対象URL（テキスト入力・https://から始まるかバリデーション）
- PageDown間隔（秒）
- PageDown回数
- F5更新までの時間（秒）
- 起動インスタンス数（1〜5のスピンボックス）

### タブ2: アカウント設定
- インスタンス数に合わせて動的にフォームを表示
- 各インスタンスに：
  - ユーザー名（テキスト入力）
  - パスワード（マスク入力）
- 「保存」ボタン → Fernetで暗号化してaccounts.jsonに書き込む
- 起動時に自動読み込み（次回入力不要）

### タブ3: ログ
- 全インスタンスのログをリアルタイム表示
- インスタンスごとに色分け
- ログ内容例：
  - 「✅ インスタンス1: ログイン完了」
  - 「⚠️ インスタンス2: 手動認証をお待ちしています...」
  - 「🔄 インスタンス3: F5更新」
  - 「❌ インスタンス4: ログイン失敗」

### 共通フッター
- 「▶ 開始」ボタン（全インスタンス一括起動）
- 「■ 停止」ボタン（全インスタンス一括停止）

## アカウント情報の暗号化（utils/crypto.py）
- 初回起動時にFernetキーを生成し `key.bin` として保存
- accounts.jsonはFernetで暗号化して保存・読み込み
- key.binとaccounts.jsonはexeと同じフォルダに配置

## コマンド
```bash
pip install -r requirements.txt
python main.py

# exeビルド
pyinstaller --onefile --windowed --name "AutoScrollBot" main.py
```

## 配布
- `dist/AutoScrollBot.exe` をUSBやGitHub Releasesで配布
- 相手の必要環境: Google Chrome のみ（Pythonは不要）

## デザイン要件
### カラー変数
- purple:      #A020B8（メイン紫）
- purple-deep: #7B0FA0（強調）
- purple-dark: #6A0080（影・最暗部）
- purple-pale: #E8D0F0（明部・ハイライト）
- cream:       #F8F2FC（背景）
- text-dark:   #2A0D38（メイン文字）
- text-mid:    #6B3A82（サブ文字）
- gold:        #E6C77A（縁取り・装飾）

### 方針
- 上品・高級感のある紫系、透明感・清潔感を重視
- 背景はcreamまたは淡いグラデーション
- グラデーションは自然に（強すぎない）
- 黒ベタ・ネオン系・派手な装飾は禁止
- tkinterのttk.Style()でカスタムスタイルを定義して適用

## コーディング規約
- 日本語コメントを使用
- 各クラス・関数にdocstring記載
- エラーはGUIのログエリアに表示
- Seleniumのdriverは各スレッドで独立して生成・破棄
