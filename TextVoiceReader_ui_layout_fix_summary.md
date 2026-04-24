# TextVoiceReader UI レイアウト修正版サマリ

## 正本
- ベース: `TextVoiceReader_outlook_mvp_impl.zip`
- 修正版: `TextVoiceReader_ui_layout_fix.zip`

## 修正目的
- テキスト入力後に読み上げ開始ボタンが見つけにくい / 表示されない問題を改善
- Outlook 設定追加により右側設定パネルが縦に長くなっても、フォーム・ボタンが隠れないように改善
- ウィンドウサイズ変更時の操作バーの崩れを抑制

## 主な修正
### 1. 上部ツールバーに読み上げ / 停止ボタンを追加
`src/text_voice_reader/ui/main_window.py`

- 上部ツールバーに `▶ 読み上げ` を追加
- 上部ツールバーに `⏹ 停止` を追加
- 下部操作バーの `▶ 再生` / `⏹ 停止` は維持
- 実行中は上部・下部のボタン状態を同期

### 2. 右側設定パネルをスクロール対応に変更
`src/text_voice_reader/ui/settings_panel.py`

- `CTkFrame` から `CTkScrollableFrame` へ変更
- ウィンドウの高さが不足しても、音声設定・出力設定・Outlook 設定へスクロールで到達可能

### 3. 下部操作バーを grid レイアウト化
`src/text_voice_reader/ui/control_panel.py`

- `pack` ベースから `grid` ベースへ変更
- 再生 / 停止ボタン、進捗バー、進捗ラベルが横幅変更時に崩れにくい構成へ変更

### 4. ウィンドウ最小サイズを少し緩和
`src/text_voice_reader/ui/main_window.py`

- `minsize(900, 600)` から `minsize(820, 520)` に変更
- 小さめの画面でも起動しやすく調整

### 5. ドキュメント更新
- `README.md`
- `docs/user_guide.md`

上部ツールバーの `▶ 読み上げ` と、右側設定パネルのスクロールについて説明を追記。

## 検証
- Python AST parse: PASS
- `py_compile` 対象 UI ファイル: PASS
- `compileall src`: PASS
- `compileall tests`: PASS

## 未実施
- Linux サンドボックス上のため、Windows GUI 表示確認と classic Outlook COM 実機確認は未実施です。

## Windows 側での確認手順
```powershell
cd path\to\text_voice_reader
python -m text_voice_reader
```

確認観点:
1. 上部ツールバーに `▶ 読み上げ` と `⏹ 停止` が表示される
2. テキストを直接入力して `▶ 読み上げ` で読み上げが開始する
3. 下部操作バーの `▶ 再生` でも同じく読み上げが開始する
4. 実行中は上部・下部の再生ボタンが disabled になり、停止ボタンが enabled になる
5. 右側設定パネルを縦スクロールできる
6. Outlook 設定の最後の `今すぐチェック` まで到達できる
7. ウィンドウサイズを小さくしても操作バーの進捗バーが大きく崩れない
