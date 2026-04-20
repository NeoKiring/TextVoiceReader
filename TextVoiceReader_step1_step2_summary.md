# TextVoiceReader 修正前サマリ（Step 1 / Step 2）

## 目的
本ドキュメントは、`TextVoiceReader` プロジェクトに対する修正作業に入る前の中間生成物として、以下を整理したものである。

- 実ファイルを確認したうえでの現状把握
- Must Fix / Should Fix のうち、今回実際にどこを直すべきか
- 大規模再設計を避けた最小差分の修正方針

今回の目的は、新機能追加ではなく、**「見栄えのよい試作」から「実務上安心して配布・保守できる品質」へ引き上げること**である。

---

## 1. 現状把握サマリ

### 1-1. プロジェクト構成の要点

- `src/text_voice_reader/`
  - `app.py` … GUI / CLI の実エントリ
  - `__main__.py` … `python -m text_voice_reader` 用エントリ
  - `orchestrator/app_orchestrator.py` … 読み込み〜分割〜TTS 実行の中核
  - `ui/` … `MainWindow`, `ControlPanel`, `LogPanel`, `UiBridge`
  - `processing/splitter.py` … 文分割
  - `config.py`, `utils/paths.py` … 設定読込とパス解決
- `config/default.toml`
  - ルート直下に存在
- `pyproject.toml`
  - packaging / 依存 / pytest 設定
- `README.md`, `docs/user_guide.md`, `docs/architecture.md`
  - 実装説明あり
- `tests/`
  - splitter / loaders / normalizer / wav_exporter / sapi5 の既存テストあり
  - ただし今回の Must Fix を直接守る回帰テストは不足

---

### 1-2. レビュー指摘と実コードの照合結果

#### Must Fix 1. LogPanel の UI スレッド unsafe 実装
実コード上でも妥当。

- `src/text_voice_reader/ui/log_panel.py`
- `logger.add(self._emit, ...)` により log sink が直接 UI 更新を実施
- `logging_setup.py` 側で `enqueue=True` のため、**別スレッドから Tk / CustomTkinter widget を触る構図**になっている

結論:
- **Must Fix としてそのまま採用すべき**

#### Must Fix 2. 部分失敗を握りつぶして成功扱い
実コード上でも妥当。

- `src/text_voice_reader/orchestrator/app_orchestrator.py`
- 文単位の例外を握って継続するが、`RunResult` に失敗件数がない
- `src/text_voice_reader/app.py` は `Done: completed/total` のみ出力
- 一部失敗でも CLI の終了コードが成功扱いになり得る

結論:
- **Must Fix としてそのまま採用すべき**

#### Must Fix 3. Pause ボタンの実装実態との不一致
実コード上でも妥当。

- `src/text_voice_reader/ui/control_panel.py` に「⏸ 一時停止」ボタンあり
- `src/text_voice_reader/ui/main_window.py` の `_action_pause()` は説明ダイアログのみ
- 実際の pause / resume は存在しない

結論:
- **未実装機能を実装済みに見せているため Must Fix**

#### Must Fix 4. README のドラッグ&ドロップ対応表記
実コード上でも妥当。

- `README.md` に D&D 対応表記あり
- 実装コード上に D&D 実装は見当たらない
- 関連依存も見当たらない

結論:
- **README の事実不一致として Must Fix**

#### Must Fix 5. `python -m text_voice_reader` 実行時の終了コード伝播
実コード上でも妥当。

- `src/text_voice_reader/__main__.py` は `main()` を呼ぶだけ
- `SystemExit(main())` になっていない
- `app.main()` の戻り値がそのまま OS 終了コードへ伝播しない

結論:
- **Must Fix**

#### Must Fix 6. `config/default.toml` の package resource / wheel 同梱
実コード上でも妥当。

- `pyproject.toml` の package-data 指定が `../config/default.toml` になっている
- パッケージ外参照であり、通常インストール前提として不安定
- `utils/paths.py` も相対探索寄りで、editable install 的な偶然動作に依存しやすい

結論:
- **Must Fix**

---

### 1-3. 実ファイルを正とした補足事項

#### package `__init__.py` の eager import について
- `src/text_voice_reader/__init__.py` 自体は軽量で、`__version__` 程度
- したがって、レビュー指摘の「package `__init__.py` の eager import」は **top-level package にはそのまま当たらない**
- 見直すなら対象は subpackage 側
  - `src/text_voice_reader/ui/__init__.py`
  - `src/text_voice_reader/loaders/__init__.py`
  - `src/text_voice_reader/processing/__init__.py`

結論:
- Should Fix として扱う場合も、**対象ファイルの特定を修正したうえで着手すべき**

#### README / docs / config コメントの事実不一致
複数あり。

- `README.md`: ドラッグ&ドロップ対応 → 実装なし
- `README.md` / `docs/user_guide.md`: pause が効くように読める箇所 → 実装なし
- `config/default.toml`: `%APPDATA%` への初回コピー前提のようなコメント → 実装側でその処理なし

結論:
- **ドキュメントは実装の事実に合わせて是正が必要**

---

## 2. 修正対象ファイル一覧

### 2-1. Must Fix の主対象
- `src/text_voice_reader/ui/log_panel.py`
- `src/text_voice_reader/ui/main_window.py`
- `src/text_voice_reader/ui/control_panel.py`
- `src/text_voice_reader/orchestrator/app_orchestrator.py`
- `src/text_voice_reader/app.py`
- `src/text_voice_reader/__main__.py`
- `src/text_voice_reader/utils/paths.py`
- `src/text_voice_reader/config.py`
- `pyproject.toml`
- `README.md`
- `docs/user_guide.md`
- `config/default.toml`
- `build/build_exe.py`（resource 配置変更の影響確認用）

### 2-2. Should Fix の主対象
- `src/text_voice_reader/processing/splitter.py`
- `tests/unit/test_splitter.py`
- `tests/` に追加する新規テスト
- `src/text_voice_reader/ui/__init__.py`
- `src/text_voice_reader/loaders/__init__.py`
- `src/text_voice_reader/processing/__init__.py`
- `pyproject.toml`（未使用依存の棚卸し）
- `README.md` / `docs/*.md` / `config/default.toml`

---

## 3. Must Fix ごとの対応ファイル

### Must Fix 1. LogPanel の UI スレッド unsafe
- 主: `src/text_voice_reader/ui/log_panel.py`
- 連動: `src/text_voice_reader/ui/main_window.py`
- 既存再利用候補: `src/text_voice_reader/ui/ui_bridge.py`

### Must Fix 2. 部分失敗を握りつぶして成功扱い
- 主: `src/text_voice_reader/orchestrator/app_orchestrator.py`
- 連動: `src/text_voice_reader/app.py`
- 連動: `src/text_voice_reader/ui/main_window.py`
- テスト: `tests/` に新規追加

### Must Fix 3. Pause ボタンの不一致
- 主: `src/text_voice_reader/ui/control_panel.py`
- 連動: `src/text_voice_reader/ui/main_window.py`
- ドキュメント: `README.md`, `docs/user_guide.md`

### Must Fix 4. README のドラッグ&ドロップ表記
- 主: `README.md`

### Must Fix 5. `python -m text_voice_reader` の終了コード伝播
- 主: `src/text_voice_reader/__main__.py`
- テスト: `tests/` に新規追加

### Must Fix 6. `config/default.toml` の package resource / wheel 同梱
- 主: `pyproject.toml`
- 主: `src/text_voice_reader/utils/paths.py`
- 連動: `src/text_voice_reader/config.py`
- 連動候補: package 内 resource 追加
- 影響確認: `build/build_exe.py`, `README.md`, `docs/user_guide.md`

---

## 4. 修正方針

### 4-1. 全体方針
- **Must Fix を先に確実に潰す**
- 既存アーキテクチャの大枠は維持する
- 大規模再設計は避け、**最小差分で品質を上げる**
- 依存追加は原則避ける
- UI では **Tk スレッド安全性を最優先**
- ドキュメントは実装の事実に合わせる

---

### 4-2. Must Fix 1: LogPanel の UI スレッド unsafe 実装
#### 方針
- `LogPanel` の log sink では widget を直接触らない
- 文字列のみを安全にキューイングする
- UI 反映は Tk メインスレッドでのみ行う
- 既存 `UiBridge` を再利用する方向が最小差分

#### 小さく済む案
- `LogPanel(master, bridge=...)` のように bridge を受け取る
- sink 側では `bridge.post(...)` のみ行う
- widget 更新処理を UI スレッド専用メソッドへ分離

#### 影響範囲
- `ui/log_panel.py`
- `ui/main_window.py`

#### テスト観点
- ログ出力中に UI が落ちないこと
- 終了時に widget 破棄後の例外が出にくいこと

---

### 4-3. Must Fix 2: 部分失敗を成功扱いにしない
#### 方針
- `RunResult` に失敗件数を持たせる
- 文単位例外の発生数を集約する
- CLI は失敗件数が 1 件でもあれば非 0 終了コードを返す
- GUI でも成功件数 / 失敗件数を明示する

#### 小さく済む案
- `RunResult.failed: int` を追加
- `orchestrator.run()` で失敗時に加算
- `app.py` の終了コードを見直す
- GUI 完了時ログへ `成功 X / 失敗 Y` を出す

#### 影響範囲
- `orchestrator/app_orchestrator.py`
- `app.py`
- `ui/main_window.py`

#### テスト観点
- 1 文だけ失敗するケース
- 全成功ケース
- 全失敗ケース
- cancel ケース

---

### 4-4. Must Fix 3: Pause ボタンの不一致
#### 方針
- 今回は真の pause/resume 実装は行わない
- **Pause ボタンを GUI から外す**のが最小差分で安全
- 関連ドキュメントも停止のみ対応へ揃える

#### 小さく済む案
- `ControlPanel` から Pause ボタン削除
- `MainWindow` の `_action_pause()` も削除
- README / user guide の pause 記述を是正

#### 影響範囲
- `ui/control_panel.py`
- `ui/main_window.py`
- `README.md`
- `docs/user_guide.md`

#### テスト観点
- GUI のボタン state が自然であること
- 実行 / 停止のみで操作破綻しないこと

---

### 4-5. Must Fix 4: README のドラッグ&ドロップ対応表記
#### 方針
- 実装が無いため README から削除
- 必要なら「ファイルを開く」「クリップボード貼り付け」等へ言い換える

#### 影響範囲
- `README.md`
- 必要なら `docs/user_guide.md`

#### テスト観点
- 文書整合のみ

---

### 4-6. Must Fix 5: `python -m text_voice_reader` の終了コード伝播
#### 方針
- `__main__.py` を `raise SystemExit(main())` へ修正する

#### 小さく済む案
- 1 ファイル 1 行レベルの変更

#### 影響範囲
- `src/text_voice_reader/__main__.py`

#### テスト観点
- `main()` の戻り値が `SystemExit(code)` に反映されること

---

### 4-7. Must Fix 6: `config/default.toml` の package resource / wheel 同梱
#### 方針
- `default.toml` を package 内 resource として扱う
- `importlib.resources` ベースで読めるようにする
- `pyproject.toml` は package 内 resource を wheel / sdist に同梱する形へ修正する
- editable install 前提の相対探索依存を減らす

#### 小さく済む案
- package 内へ `default.toml` を置く
- `config.py` / `utils/paths.py` で package resource を読む
- ルート `config/default.toml` は開発用コピーとして残すか、整理方針を別途決める
- ただし、**実行時の正本は package resource** に寄せる

#### 影響範囲
- `pyproject.toml`
- `src/text_voice_reader/utils/paths.py`
- `src/text_voice_reader/config.py`
- package 内 resource 追加
- `build/build_exe.py`
- `README.md`, `docs/user_guide.md`

#### テスト観点
- user config がなくても package default から起動できること
- 通常 install 前提で設定読込が壊れないこと

---

## 5. 優先順位付きの実装順

1. `src/text_voice_reader/ui/log_panel.py`
2. `src/text_voice_reader/ui/main_window.py`
3. `src/text_voice_reader/orchestrator/app_orchestrator.py`
4. `src/text_voice_reader/app.py`
5. `src/text_voice_reader/ui/control_panel.py`
6. `src/text_voice_reader/__main__.py`
7. `src/text_voice_reader/utils/paths.py`
8. `src/text_voice_reader/config.py`
9. `pyproject.toml`
10. `README.md`
11. `docs/user_guide.md`

---

## 6. Should Fix の扱い

今回の本線は **Must Fix + それを守る最低限の回帰テスト** とする。

Should Fix は、Must Fix 完了後に以下順で実施するのが妥当。

1. `processing/splitter.py` の英語誤分割の最低限改善
2. ウィンドウ close 時の終了処理改善
3. README / config コメントの事実不一致修正
4. 未使用依存の棚卸し
5. subpackage `__init__.py` の eager import 整理

---

## 7. 実装前の結論

今回の修正は、実ファイルを見る限り **Must Fix の大半が実害あり** であり、特に以下の 4 点が優先度高である。

- `LogPanel` の Tk スレッド違反
- `RunResult` が失敗件数を持たず、CLI も成功扱いしやすいこと
- Pause ボタンが未実装なのに実装済みに見えること
- package resource / wheel 同梱が通常インストールに弱いこと

したがって、次工程では以下の方針で実装に入る。

- UI スレッド安全性の確保
- 失敗の可視化と終了コード是正
- 未実装機能の表示是正
- 配布可能性を下げる packaging / config 読込の是正
- Must Fix を守るための最低限テスト追加

以上。
