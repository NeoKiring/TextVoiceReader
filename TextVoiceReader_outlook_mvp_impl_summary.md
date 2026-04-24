# TextVoiceReader Outlook MVP Implementation Summary

## 実装内容

- Outlook COM 読み取り Spike script を継続同梱
- `src/text_voice_reader/integrations/outlook/` を追加
  - `models.py`: COM 非依存の `OutlookMailSnapshot`
  - `com_client.py`: classic Outlook COM 読み取り、MailItem 変換、既読化
  - `monitor.py`: polling thread / duplicate detection / startup 既存メールスキップ
  - `sanitizer.py`: 本文プレビュー・全文読み上げ前処理
  - `formatter.py`: 差出人・件名・本文冒頭・全文の読み上げ文生成
- `[outlook]` 設定セクションを `default.toml` / `config/default.toml` / `AppConfig` に追加
- GUI SettingsPanel に Outlook セクションを追加
  - 新着メール読み上げ ON/OFF
  - 未読のみ
  - 差出人 / 件名 / 本文冒頭
  - 冒頭後に全文読み上げ確認
  - 本文冒頭文字数
  - 監視間隔
  - 今すぐチェック
- MainWindow に Outlook monitor 統合を追加
  - Outlook COM は monitor thread 側
  - Tk dialog は main thread 側
  - SAPI5 読み上げは既存 orchestrator worker 側
  - Outlook メール読み上げでは `save_wav=False` を強制
- README / user guide / architecture / outlook integration doc を更新
- Outlook 関連 unit tests を追加

## 検証

- `compileall`:
  - `src`: PASS
  - `tests`: PASS
- 追加 Outlook 関連 tests:
  - 8 passed
- 影響範囲の既存 tests:
  - 14 passed

## 注意

- 実 Outlook COM の GUI 統合動作は、このサンドボックスでは Windows / classic Outlook がないため未実行です。
- `build/lib` は古い生成物が混ざらないよう削除しています。配布時は再ビルドしてください。
