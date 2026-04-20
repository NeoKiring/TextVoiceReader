# TextVoiceReader 手元確認の実施順序をまとめた運用手順書（詳細版）

## 目的
この手順書は、TextVoiceReader の修正版を **手元 Windows 環境で安全に確認するための実施順序** をまとめたものです。  
目的は、確認漏れを防ぎつつ、**Must Fix が実運用で本当に潰れているか** を短時間で判定できるようにすることです。

この手順書は、以下の順で進めます。

1. 作業前準備
2. 自動テスト確認
3. GUI の短時間スモークテスト
4. GUI の重点確認
5. CLI / 終了コード確認
6. package / wheel 確認
7. README / ドキュメント整合確認
8. 総合判定と記録

---

# 0. 前提
## 対象
- TextVoiceReader の今回の修正版
- 手元の Windows 環境
- Python 実行環境があること
- GUI が起動できること

## この手順書で特に確認するもの
- LogPanel の UI スレッド安全性
- 部分失敗が成功扱いに見えないこと
- Pause ボタン除去後の UI 整合
- `python -m text_voice_reader` の終了コード伝播
- package resource 化した `default.toml` の読込
- 実行中 close の安全性
- README / user guide と実装の一致

---

# 1. 作業前準備（最初に必ず実施）

## 1-1. 修正版の配置
1. 修正版 zip を展開する
2. 展開先のフォルダ名を確認する
3. そのフォルダを作業ディレクトリとして使用する

### 確認
- [ ] 展開に失敗していない
- [ ] 古い別バージョンと混ざっていない
- [ ] 作業対象フォルダが明確

---

## 1-2. Python 仮想環境の準備
PowerShell 例:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

必要依存を入れる:

```powershell
pip install -e .
```

### 確認
- [ ] 仮想環境が有効化されている
- [ ] `python --version` が想定通り
- [ ] `pip install -e .` が通る

### NG の場合
- install エラーが出たら、その時点で先に修正
- 先へ進まない

---

## 1-3. 確認用ファイルの準備
以下を用意する。

### 正常系
- 短文テキスト
- 中程度の長さのテキスト
- 英文混在テキスト

### 境界 / 異常系
- 空ファイル
- 句読点の少ない文章
- `Dr.`, `Mr.`, `e.g.` を含む英文
- 一部失敗を起こせる条件の入力（あれば）

### 出力先
- 専用の出力フォルダを作る

### 確認
- [ ] 入力ファイルが揃っている
- [ ] 出力先フォルダが空または整理済み
- [ ] 書き込み権限がある

---

# 2. 自動テスト確認（最初の足切り）

## 2-1. まず今回追加の回帰テストを回す
```powershell
$env:PYTHONPATH="src"
pytest -q tests/unit/test_app_cli.py tests/unit/test_orchestrator_run_result.py tests/unit/test_config_paths.py tests/unit/test_splitter.py
python -m compileall -q src
```

### 合格条件
- pytest が pass
- compileall がエラーなし

### 確認
- [ ] 回帰テスト成功
- [ ] 構文チェック成功

### NG の場合
- ここで止める
- GUI 確認へ進まない

---

## 2-2. 余力があれば既存 test 一式も回す
```powershell
$env:PYTHONPATH="src"
pytest -q
```

### 確認
- [ ] 全体 test を回した
- [ ] 既知要因以外の失敗がない

### 注意
- 依存やローカル条件で一部失敗する場合は、その理由を記録してから先へ進む

---

# 3. GUI の短時間スモークテスト（最短で壊れていないか見る）

## 3-1. GUI 起動
```powershell
python -m text_voice_reader
```

### 確認
- [ ] GUI が起動する
- [ ] 起動直後に traceback が出ない
- [ ] Pause / 一時停止ボタンが表示されていない
- [ ] ログ欄が見える
- [ ] Start / Stop など基本ボタンが使えそう

### NG の場合
- ここで止める
- 起動ログと traceback を保存する

---

## 3-2. 正常系 1 回実行
1. 短文テキストを読み込む
2. 出力先を設定
3. 実行
4. 完了まで待つ

### 確認
- [ ] 実行開始できる
- [ ] ログが表示される
- [ ] 完了する
- [ ] 出力が生成される
- [ ] 完了後に再操作できる

### 合格基準
- 1 回の正常実行が最後まで通る

### NG の場合
- ここで止める
- GUI の重点確認へ進まない

---

# 4. GUI の重点確認（Must Fix 観点を潰す）

# 4-1. LogPanel スレッド安全性
## 手順
1. 中程度以上のテキストを読み込む
2. 実行する
3. 処理中にウィンドウ移動、最小化、再表示を行う
4. ログの増え方を観察する

### 確認
- [ ] ログ更新中に固まらない
- [ ] `_tkinter.TclError` が出ない
- [ ] ログ欄が壊れない
- [ ] 完了後もログが正常

### 合格基準
- ログ多発時でも Tk 例外なし
- UI 応答性が極端に崩れない

### NG の場合
- 直ちにログを保存
- 「ログ更新中」「close 中」「完了直前」など発生タイミングを記録

---

# 4-2. Stop 操作
## 手順
1. 長めのテキストで実行開始
2. 数文進んだら Stop
3. 停止完了まで確認

### 確認
- [ ] Stop が受け付けられる
- [ ] 停止中にフリーズしない
- [ ] 全成功のような誤表示にならない
- [ ] 停止後に再操作できる

### 合格基準
- Stop 後の状態が利用者にとって誤解の少ないものになっている

---

# 4-3. 部分失敗の見え方
## 手順
1. 一部だけ失敗する条件で実行
2. 完了表示とログを確認

### 確認
- [ ] 成功件数と失敗件数が区別されている
- [ ] 全成功のように見えない
- [ ] ログで一部失敗が分かる

### 合格基準
- 利用者が「一部失敗した」と判断できる

---

# 4-4. close 時の安全性
## 手順 A: 非実行中 close
1. GUI 起動
2. 何もせず閉じる

### 確認
- [ ] 正常に閉じる
- [ ] 例外なし

## 手順 B: 実行中 close
1. 長めのテキストを実行
2. ログが出ている最中に閉じる

### 確認
- [ ] 致命的エラーなし
- [ ] `_tkinter.TclError` なし
- [ ] プロセスが残りにくい
- [ ] 次回起動に影響なし

### 合格基準
- 実行中 close でも大きく壊れない

### NG の場合
- 発生タイミングを必ず記録
- close 直前の操作内容も残す

---

# 4-5. 複数回連続実行
## 手順
1. 正常系を 2〜3 回連続実行
2. 必要なら途中で Stop を挟む

### 確認
- [ ] 2 回目以降も正常開始できる
- [ ] ログが不自然に重複しない
- [ ] 前回状態が汚染されていない

### 合格基準
- 1 回目だけ成功する状態でない

---

# 4-6. 英文 splitter の最低限確認
## 入力例
- `Dr. Smith went home. He was tired.`
- `This is an example, e.g. a simple test. It should continue.`
- `Mr. Brown arrived at 5 p.m. He left soon after.`

### 確認
- [ ] `Dr.` で不自然分割しない
- [ ] `Mr.` で不自然分割しない
- [ ] `e.g.` の扱いが極端に悪くない
- [ ] 日本語文に悪影響がない

### 合格基準
- 最低限の改善が目視で確認できる

---

# 5. CLI / 終了コード確認

## 5-1. help 表示
```powershell
python -m text_voice_reader --help
$LASTEXITCODE
```

### 確認
- [ ] help が表示される
- [ ] 終了コードが想定通り

---

## 5-2. 正常系終了コード
正常系入力で CLI 実行する。

### 確認
- [ ] 終了コード 0
- [ ] 成功件数表示が妥当
- [ ] 失敗なし

### 記録
- 実行コマンド
- 終了コード
- 出力

---

## 5-3. 部分失敗時終了コード
一部失敗条件で CLI 実行する。

### 確認
- [ ] 終了コードが非 0
- [ ] `failed` 件数が見える
- [ ] 全成功に見えない

### 合格基準
- 失敗が 1 件でもあれば成功扱いしない

---

# 6. package / wheel 確認

## 6-1. wheel 作成
```powershell
python -m pip install build
python -m build
```

### 確認
- [ ] wheel / sdist が作れる
- [ ] ビルドエラーがない

---

## 6-2. 別環境 install 確認
可能なら新しい仮想環境で実施する。

```powershell
python -m venv .venv_clean
.\.venv_clean\Scripts\Activate.ps1
pip install dist\*.whl
python -m text_voice_reader --help
```

### 確認
- [ ] install 成功
- [ ] source tree 外でも起動可能
- [ ] `default.toml` 読込で失敗しない

### 合格基準
- editable install の偶然動作に依存していない

---

# 7. README / ドキュメント整合確認

## 手順
README、user guide、config コメントをざっと見直す。

### 確認
- [ ] ドラッグ&ドロップ対応と書いていない
- [ ] Pause 実装済みのように書いていない
- [ ] config 説明が現在実装と一致
- [ ] 操作説明が UI と一致

### 合格基準
- 実装事実と文書にズレがない

---

# 8. 総合判定

## 8-1. 合格条件
以下を満たしたら、今回の修正版は「手元確認 OK」としてよい。

- [ ] 回帰テスト OK
- [ ] GUI 起動 OK
- [ ] 正常系実行 OK
- [ ] LogPanel の重点確認 OK
- [ ] Stop / close OK
- [ ] 部分失敗表示 OK
- [ ] CLI 終了コード OK
- [ ] package / wheel OK
- [ ] docs 整合 OK

---

## 8-2. 見送り条件
以下のどれかがあれば配布前確認 NG。

- [ ] 実行中 close で再現性のあるクラッシュ
- [ ] `_tkinter.TclError` が出る
- [ ] 一部失敗が全成功に見える
- [ ] `python -m text_voice_reader` の終了コードが不正
- [ ] 通常 install で `default.toml` 読込に失敗
- [ ] README が実装とズレている

---

# 9. 実施記録テンプレート

## 実施情報
- 実施日:
- 実施者:
- 対象ブランチ / commit:
- OS:
- Python:
- 実施場所:
- 備考:

## 確認結果
- 回帰テスト:
- GUI 起動:
- 正常系実行:
- LogPanel:
- Stop:
- close:
- 部分失敗:
- CLI 終了コード:
- package / wheel:
- docs 整合:
- 総合判定:

## 発見事項
1.
2.
3.

## 次アクション
- [ ] そのまま配布前最終確認へ進む
- [ ] 修正して再確認
- [ ] 既知事項として記録
