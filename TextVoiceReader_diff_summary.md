# TextVoiceReader 修正差分サマリ

## src/text_voice_reader/ui/log_panel.py

```diff
--- a/src/text_voice_reader/ui/log_panel.py
+++ b/src/text_voice_reader/ui/log_panel.py
@@ -4,6 +4,8 @@
 
 import customtkinter as ctk
 from loguru import logger
+
+from text_voice_reader.ui.ui_bridge import UiBridge
 
 
 class LogPanel(ctk.CTkFrame):
@@ -14,9 +16,17 @@
 
     _MAX_LINES = 500
 
-    def __init__(self, master: ctk.CTkBaseClass, **kwargs) -> None:
+    def __init__(
+        self,
+        master: ctk.CTkBaseClass,
+        *,
+        bridge: UiBridge,
+        **kwargs,
+    ) -> None:
         super().__init__(master, **kwargs)
+        self._bridge = bridge
         self._expanded = False
+        self._is_destroyed = False
 
         self._toggle_btn = ctk.CTkButton(
             self,
@@ -39,7 +49,8 @@
         )
         self._textbox.pack(fill="both", expand=True, padx=4, pady=4)
 
-        # Register loguru sink. The binding survives as long as this widget does.
+        # Register loguru sink. The sink must not touch Tk widgets directly
+        # because logger callbacks may execute on a non-UI thread.
         self._sink_id = logger.add(self._emit, level="INFO")
 
     # -----------------------------------------------------------------
@@ -62,8 +73,15 @@
 
     def _emit(self, message) -> None:  # noqa: ANN001
         """Loguru sink callable. Receives a formatted message."""
+        if self._is_destroyed:
+            return
+        self._bridge.post(self._append_text, str(message))
+
+    def _append_text(self, text: str) -> None:
+        """Append text on the Tk thread only."""
+        if self._is_destroyed or not self.winfo_exists():
+            return
         try:
-            text = str(message)
             self._textbox.configure(state="normal")
             self._textbox.insert("end", text)
             # Trim to last N lines to avoid unbounded growth
@@ -78,6 +96,7 @@
             pass
 
     def destroy(self) -> None:  # type: ignore[override]
+        self._is_destroyed = True
         try:
             logger.remove(self._sink_id)
         except Exception:
```

## src/text_voice_reader/ui/control_panel.py

```diff
--- a/src/text_voice_reader/ui/control_panel.py
+++ b/src/text_voice_reader/ui/control_panel.py
@@ -1,4 +1,4 @@
-"""Bottom control panel: play/pause/stop buttons and progress bar."""
+"""Bottom control panel: play/stop buttons and progress bar."""
 
 from __future__ import annotations
 
@@ -8,35 +8,29 @@
 
 
 class ControlPanel(ctk.CTkFrame):
-    """Play / pause / stop buttons plus a text progress indicator."""
+    """Play / stop buttons plus a text progress indicator."""
 
     def __init__(
         self,
         master: ctk.CTkBaseClass,
         *,
         on_play: Callable[[], None],
-        on_pause: Callable[[], None],
         on_stop: Callable[[], None],
         **kwargs,
     ) -> None:
         super().__init__(master, **kwargs)
 
         self._on_play = on_play
-        self._on_pause = on_pause
         self._on_stop = on_stop
 
         self._btn_play = ctk.CTkButton(
             self, text="▶ 再生", width=100, command=self._handle_play
-        )
-        self._btn_pause = ctk.CTkButton(
-            self, text="⏸ 一時停止", width=100, command=self._handle_pause, state="disabled"
         )
         self._btn_stop = ctk.CTkButton(
             self, text="⏹ 停止", width=100, command=self._handle_stop, state="disabled"
         )
 
         self._btn_play.pack(side="left", padx=4, pady=8)
-        self._btn_pause.pack(side="left", padx=4, pady=8)
         self._btn_stop.pack(side="left", padx=4, pady=8)
 
         self._progress_var = ctk.StringVar(value="準備完了")
@@ -55,11 +49,9 @@
         """Toggle button enabled/disabled states based on run state."""
         if running:
             self._btn_play.configure(state="disabled")
-            self._btn_pause.configure(state="normal")
             self._btn_stop.configure(state="normal")
         else:
             self._btn_play.configure(state="normal")
-            self._btn_pause.configure(state="disabled")
             self._btn_stop.configure(state="disabled")
 
     def set_progress(self, current: int, total: int, label: str = "") -> None:
@@ -84,9 +76,6 @@
     def _handle_play(self) -> None:
         self._on_play()
 
-    def _handle_pause(self) -> None:
-        self._on_pause()
-
     def _handle_stop(self) -> None:
         self._on_stop()
 
```

## src/text_voice_reader/ui/main_window.py

```diff
--- a/src/text_voice_reader/ui/main_window.py
+++ b/src/text_voice_reader/ui/main_window.py
@@ -10,7 +10,7 @@
 |   Preview (editable)       |   Settings (voice / output)      |
 |                            |                                  |
 +----------------------------+----------------------------------+
-| Control bar: ▶ ⏸ ⏹    progress bar                            |
+| Control bar: ▶ ⏹    progress bar                              |
 +---------------------------------------------------------------+
 | ▸ Log (collapsible)                                           |
 +---------------------------------------------------------------+
@@ -18,7 +18,6 @@
 
 from __future__ import annotations
 
-import sys
 from pathlib import Path
 from tkinter import filedialog, messagebox
 
@@ -28,9 +27,8 @@
 from text_voice_reader import __version__
 from text_voice_reader.config import AppConfig
 from text_voice_reader.logging_setup import get_logger
-from text_voice_reader.orchestrator import AppOrchestrator
+from text_voice_reader.orchestrator import AppOrchestrator, RunResult
 from text_voice_reader.processing.splitter import Sentence
-from text_voice_reader.tts.options import SynthesisOptions
 from text_voice_reader.ui.control_panel import ControlPanel
 from text_voice_reader.ui.log_panel import LogPanel
 from text_voice_reader.ui.preview_panel import PreviewPanel
@@ -51,7 +49,8 @@
         self._current_sentences: list[Sentence] = []
         self._current_source = "input"
         self._stop_token: StopToken | None = None
-        self._speech_handle = None  # for SAPI5 pause/resume on async speak
+        self._worker_thread = None
+        self._closing = False
 
         # Window configuration
         ctk.set_appearance_mode(cfg.app.theme)
@@ -119,21 +118,24 @@
         self._control = ControlPanel(
             self,
             on_play=self._action_play,
-            on_pause=self._action_pause,
             on_stop=self._action_stop,
         )
         self._control.pack(fill="x", padx=8, pady=(0, 6))
 
         # Log panel
-        self._log_panel = LogPanel(self)
+        self._log_panel = LogPanel(self, bridge=self._bridge)
         self._log_panel.pack(fill="x", padx=8, pady=(0, 8))
 
     def _bind_close(self) -> None:
         self.protocol("WM_DELETE_WINDOW", self._on_close)
 
     def _on_close(self) -> None:
+        if self._closing:
+            return
+        self._closing = True
         if self._stop_token is not None:
             self._stop_token.set()
+        self._control.set_running(False)
         self._bridge.shutdown()
         self.after(100, self.destroy)
 
@@ -227,21 +229,13 @@
         self._control.set_running(True)
         self._control.set_progress(0, len(sentences))
 
-        run_in_thread(
+        self._worker_thread = run_in_thread(
             self._worker_run,
             sentences,
             runtime_cfg.output.play,
             runtime_cfg.output.save_wav,
             self._stop_token,
             name="tvr-run-worker",
-        )
-
-    def _action_pause(self) -> None:
-        # With HybridSink + winsound, pause is not natively supported.
-        # We fall back to full stop for now and log the behavior.
-        messagebox.showinfo(
-            "一時停止",
-            "文の境界では一時停止できません。停止してから再度 ▶ 再生してください。",
         )
 
     def _action_stop(self) -> None:
@@ -278,20 +272,42 @@
             self._bridge.post(self._on_run_complete, result)
         except Exception as e:
             _log.exception(f"Run failed: {e}")
-            self._bridge.post(
-                messagebox.showerror, "実行エラー", str(e)
-            )
-            self._bridge.post(self._control.set_running, False)
-
-    def _on_run_complete(self, result) -> None:  # noqa: ANN001
+            if not self._closing:
+                self._bridge.post(
+                    messagebox.showerror, "実行エラー", str(e)
+                )
+                self._bridge.post(self._control.set_running, False)
+
+    def _on_run_complete(self, result: RunResult) -> None:
+        if self._closing:
+            return
+
         self._control.set_running(False)
         self._preview.clear_highlight()
+        self._stop_token = None
+        self._worker_thread = None
+
         if result.cancelled:
             self._control.reset_progress()
             _log.info("Run cancelled")
             return
+
+        summary = (
+            f"Run complete: success={result.completed}, failed={result.failed}, "
+            f"total={result.total_sentences}"
+        )
         if result.output_wav:
             _log.info(f"Output saved: {result.output_wav}")
+        _log.info(summary)
+
+        if result.failed > 0:
+            messagebox.showwarning(
+                "一部失敗",
+                "一部の文の読み上げまたは保存に失敗しました。\n"
+                f"成功: {result.completed}\n"
+                f"失敗: {result.failed}\n"
+                f"合計: {result.total_sentences}",
+            )
 
     # -----------------------------------------------------------------
     # Helpers
```

## src/text_voice_reader/orchestrator/app_orchestrator.py

```diff
--- a/src/text_voice_reader/orchestrator/app_orchestrator.py
+++ b/src/text_voice_reader/orchestrator/app_orchestrator.py
@@ -44,6 +44,7 @@
 
     total_sentences: int
     completed: int
+    failed: int
     output_wav: Path | None
     cancelled: bool
 
@@ -172,6 +173,7 @@
 
         total = len(sentences)
         completed = 0
+        failed = 0
         with HybridSink(
             engine,
             play=play_flag,
@@ -184,6 +186,7 @@
                     return RunResult(
                         total_sentences=total,
                         completed=completed,
+                        failed=failed,
                         output_wav=save_path,
                         cancelled=True,
                     )
@@ -193,14 +196,19 @@
                     if progress is not None:
                         progress(idx, total, sentence)
                 except Exception as e:
+                    failed += 1
                     _log.exception(f"Failed on sentence {sentence.id}: {e}")
                     # Continue with next sentence rather than abort full run
                     continue
 
-        _log.info(f"Run complete: {completed}/{total} sentences, output={save_path}")
+        _log.info(
+            f"Run complete: completed={completed}, failed={failed}, "
+            f"total={total}, output={save_path}"
+        )
         return RunResult(
             total_sentences=total,
             completed=completed,
+            failed=failed,
             output_wav=save_path,
             cancelled=False,
         )
```

## src/text_voice_reader/app.py

```diff
--- a/src/text_voice_reader/app.py
+++ b/src/text_voice_reader/app.py
@@ -137,9 +137,19 @@
         except OSError as e:
             print(f"Warning: could not move output: {e}", file=sys.stderr)
 
-    print(f"Done: {result.completed}/{result.total_sentences} sentences", file=sys.stderr)
+    print(
+        "Done: "
+        f"success={result.completed} "
+        f"failed={result.failed} "
+        f"total={result.total_sentences}",
+        file=sys.stderr,
+    )
     if result.output_wav:
         print(f"Output WAV: {result.output_wav}")
+    if result.cancelled:
+        return 130
+    if result.failed > 0:
+        return 1
     return 0 if result.completed > 0 else 1
 
 
```

## src/text_voice_reader/utils/paths.py

```diff
--- a/src/text_voice_reader/utils/paths.py
+++ b/src/text_voice_reader/utils/paths.py
@@ -1,11 +1,13 @@
-"""Path helpers (config locations, user data dirs, package resources)."""
+"""Filesystem / app-data path helpers."""
 
 from __future__ import annotations
 
 import os
 import sys
 from functools import lru_cache
+from importlib.resources import files
 from pathlib import Path
+from tempfile import NamedTemporaryFile
 
 APP_NAME = "TextVoiceReader"
 
@@ -17,25 +19,35 @@
 
 
 @lru_cache(maxsize=1)
+def get_packaged_config_text() -> str:
+    """Read the packaged default config as UTF-8 text."""
+    try:
+        return files("text_voice_reader").joinpath("default.toml").read_text(
+            encoding="utf-8"
+        )
+    except FileNotFoundError as exc:  # pragma: no cover - packaging error
+        raise RuntimeError("Packaged default.toml is missing") from exc
+
+
+@lru_cache(maxsize=1)
 def get_package_config_path() -> Path:
-    """Return the path to the packaged ``config/default.toml``.
+    """Return a readable filesystem path for the packaged ``default.toml``.
 
-    This works both in a normal install (egg/wheel) and when running from a
-    source checkout. We walk up from the package root looking for a sibling
-    ``config`` directory.
+    The default config is shipped inside the ``text_voice_reader`` package so it
+    is available in normal installations, wheels, and source checkouts.
     """
-    pkg_root = get_package_root()
-    # Check common relative locations
-    candidates = [
-        pkg_root.parent.parent / "config" / "default.toml",  # src layout
-        pkg_root.parent / "config" / "default.toml",
-        pkg_root / "config" / "default.toml",
-    ]
-    for c in candidates:
-        if c.is_file():
-            return c
-    # Fallback: return the first candidate even if it doesn't exist
-    return candidates[0]
+    candidate = get_package_root() / "default.toml"
+    if candidate.is_file():
+        return candidate
+
+    with NamedTemporaryFile(
+        mode="w",
+        encoding="utf-8",
+        suffix="_text_voice_reader_default.toml",
+        delete=False,
+    ) as tmp:
+        tmp.write(get_packaged_config_text())
+        return Path(tmp.name)
 
 
 def get_user_data_dir() -> Path:
@@ -80,6 +92,7 @@
     "APP_NAME",
     "get_package_root",
     "get_package_config_path",
+    "get_packaged_config_text",
     "get_user_data_dir",
     "get_user_config_path",
     "get_user_log_dir",
```

## src/text_voice_reader/config.py

```diff
--- a/src/text_voice_reader/config.py
+++ b/src/text_voice_reader/config.py
@@ -3,7 +3,7 @@
 The configuration uses a layered approach:
 
 1. Defaults baked into the pydantic models.
-2. ``config/default.toml`` shipped with the package.
+2. ``default.toml`` shipped inside the package.
 3. User override at ``%APPDATA%/TextVoiceReader/config.toml`` (Windows) or
    ``~/.config/TextVoiceReader/config.toml`` (Linux/macOS for dev).
 4. Environment variables prefixed with ``TVR_``.
@@ -19,7 +19,6 @@
 
 from __future__ import annotations
 
-import os
 import tomllib
 from pathlib import Path
 from typing import Any, Literal
@@ -28,7 +27,7 @@
 from pydantic_settings import BaseSettings, SettingsConfigDict
 
 from text_voice_reader.utils.paths import (
-    get_package_config_path,
+    get_packaged_config_text,
     get_user_config_path,
     resolve_user_path,
 )
@@ -124,6 +123,10 @@
         return tomllib.load(f)
 
 
+def _read_packaged_default() -> dict[str, Any]:
+    return tomllib.loads(get_packaged_config_text())
+
+
 def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
     """Recursive dict merge. Values in ``override`` win."""
     out = dict(base)
@@ -144,7 +147,7 @@
     Returns:
         Fully merged :class:`AppConfig`.
     """
-    package_default = _read_toml(get_package_config_path())
+    package_default = _read_packaged_default()
     user_path = user_config_path or get_user_config_path()
     user_data = _read_toml(user_path)
     merged = _deep_merge(package_default, user_data)
```

## src/text_voice_reader/processing/splitter.py

```diff
--- a/src/text_voice_reader/processing/splitter.py
+++ b/src/text_voice_reader/processing/splitter.py
@@ -6,13 +6,36 @@
 from dataclasses import dataclass
 from typing import Iterable
 
-# Primary sentence terminators: Japanese full stops, English periods, exclamation, question marks.
-_TERMINATORS = re.compile(r"(?<=[。！？!?\.])\s*")
+# Primary sentence terminators: Japanese full stops, English periods,
+# exclamation marks, and question marks.
+# Periods are only treated as sentence boundaries when followed by whitespace,
+# closing punctuation, or end-of-string so that common abbreviations like
+# "e.g." / "U.S." / "Dr." are not split into tiny fragments.
+_TERMINATORS = re.compile(
+    r"(?<=[。！？!?])\s*|(?<=\.)(?=(?:\s+|[\"'”’）】\]\)]|$))\s*"
+)
 # Soft break candidates used when a chunk is still too long
 _SOFT_BREAKS = re.compile(r"(?<=[、,;:])\s*")
 # Characters considered "proper" sentence endings - we do NOT merge fragments
 # that already end with one of these into the next, even if they are short.
 _TERMINATOR_CHARS = "。！？!?."
+# Common abbreviations that should stay attached to the following sentence part.
+_EN_ABBREVIATIONS = {
+    "dr.",
+    "mr.",
+    "mrs.",
+    "ms.",
+    "prof.",
+    "sr.",
+    "jr.",
+    "st.",
+    "vs.",
+    "etc.",
+    "e.g.",
+    "i.e.",
+    "u.s.",
+    "u.k.",
+}
 
 
 @dataclass(frozen=True)
@@ -54,6 +77,7 @@
         if not text:
             return []
         hard = [s for s in _TERMINATORS.split(text) if s and s.strip()]
+        hard = list(self._merge_english_abbreviations(hard))
         fragments: list[str] = []
         for frag in hard:
             fragments.extend(self._soft_split(frag))
@@ -92,6 +116,27 @@
         n = self._opts.max_chars
         return [text[i : i + n] for i in range(0, len(text), n)]
 
+    def _merge_english_abbreviations(self, fragments: Iterable[str]) -> Iterable[str]:
+        """Keep common English abbreviations attached to the following text."""
+        buf = ""
+        for fragment in fragments:
+            if buf:
+                joiner = " " if buf.rstrip().endswith(".") else ""
+                candidate = f"{buf}{joiner}{fragment.lstrip()}"
+            else:
+                candidate = fragment
+            normalized = candidate.strip().lower()
+            if normalized in _EN_ABBREVIATIONS:
+                buf = candidate
+                continue
+            if buf:
+                yield candidate
+                buf = ""
+            else:
+                yield fragment
+        if buf:
+            yield buf
+
     def _merge_short(self, fragments: Iterable[str]) -> Iterable[str]:
         """Coalesce sub-threshold fragments with the previous one.
 
```

## src/text_voice_reader/ui/__init__.py

```diff
--- a/src/text_voice_reader/ui/__init__.py
+++ b/src/text_voice_reader/ui/__init__.py
@@ -1,11 +1,17 @@
 """CustomTkinter-based UI layer."""
 
-from text_voice_reader.ui.control_panel import ControlPanel
-from text_voice_reader.ui.log_panel import LogPanel
-from text_voice_reader.ui.main_window import MainWindow
-from text_voice_reader.ui.preview_panel import PreviewPanel
-from text_voice_reader.ui.settings_panel import SettingsPanel
-from text_voice_reader.ui.ui_bridge import UiBridge
+from __future__ import annotations
+
+from importlib import import_module
+from typing import TYPE_CHECKING, Any
+
+if TYPE_CHECKING:
+    from text_voice_reader.ui.control_panel import ControlPanel
+    from text_voice_reader.ui.log_panel import LogPanel
+    from text_voice_reader.ui.main_window import MainWindow
+    from text_voice_reader.ui.preview_panel import PreviewPanel
+    from text_voice_reader.ui.settings_panel import SettingsPanel
+    from text_voice_reader.ui.ui_bridge import UiBridge
 
 __all__ = [
     "ControlPanel",
@@ -15,3 +21,19 @@
     "SettingsPanel",
     "UiBridge",
 ]
+
+_MODULE_BY_NAME = {
+    "ControlPanel": "text_voice_reader.ui.control_panel",
+    "LogPanel": "text_voice_reader.ui.log_panel",
+    "MainWindow": "text_voice_reader.ui.main_window",
+    "PreviewPanel": "text_voice_reader.ui.preview_panel",
+    "SettingsPanel": "text_voice_reader.ui.settings_panel",
+    "UiBridge": "text_voice_reader.ui.ui_bridge",
+}
+
+
+def __getattr__(name: str) -> Any:
+    if name not in _MODULE_BY_NAME:
+        raise AttributeError(name)
+    module = import_module(_MODULE_BY_NAME[name])
+    return getattr(module, name)
```

## src/text_voice_reader/loaders/__init__.py

```diff
--- a/src/text_voice_reader/loaders/__init__.py
+++ b/src/text_voice_reader/loaders/__init__.py
@@ -1,21 +1,27 @@
 """File-format loaders that produce plain UTF-8 text."""
 
-from text_voice_reader.loaders.base import (
-    LoaderError,
-    TextLoader,
-    TvrError,
-    UnsupportedFormatError,
-)
-from text_voice_reader.loaders.csv_loader import CsvLoader
-from text_voice_reader.loaders.docx_loader import DocxLoader
-from text_voice_reader.loaders.encoding import DetectionResult, detect_encoding, read_text_auto
-from text_voice_reader.loaders.factory import LoaderFactory
-from text_voice_reader.loaders.html_loader import HtmlLoader
-from text_voice_reader.loaders.markdown_loader import MarkdownLoader
-from text_voice_reader.loaders.msg_loader import MsgLoader
-from text_voice_reader.loaders.pdf_loader import PdfLoader
-from text_voice_reader.loaders.pptx_loader import PptxLoader
-from text_voice_reader.loaders.txt_loader import TxtLoader
+from __future__ import annotations
+
+from importlib import import_module
+from typing import TYPE_CHECKING, Any
+
+if TYPE_CHECKING:
+    from text_voice_reader.loaders.base import (
+        LoaderError,
+        TextLoader,
+        TvrError,
+        UnsupportedFormatError,
+    )
+    from text_voice_reader.loaders.csv_loader import CsvLoader
+    from text_voice_reader.loaders.docx_loader import DocxLoader
+    from text_voice_reader.loaders.encoding import DetectionResult, detect_encoding, read_text_auto
+    from text_voice_reader.loaders.factory import LoaderFactory
+    from text_voice_reader.loaders.html_loader import HtmlLoader
+    from text_voice_reader.loaders.markdown_loader import MarkdownLoader
+    from text_voice_reader.loaders.msg_loader import MsgLoader
+    from text_voice_reader.loaders.pdf_loader import PdfLoader
+    from text_voice_reader.loaders.pptx_loader import PptxLoader
+    from text_voice_reader.loaders.txt_loader import TxtLoader
 
 __all__ = [
     "CsvLoader",
@@ -35,3 +41,33 @@
     "detect_encoding",
     "read_text_auto",
 ]
+
+_ATTR_SOURCES = {
+    "CsvLoader": ("text_voice_reader.loaders.csv_loader", "CsvLoader"),
+    "DetectionResult": ("text_voice_reader.loaders.encoding", "DetectionResult"),
+    "DocxLoader": ("text_voice_reader.loaders.docx_loader", "DocxLoader"),
+    "HtmlLoader": ("text_voice_reader.loaders.html_loader", "HtmlLoader"),
+    "LoaderError": ("text_voice_reader.loaders.base", "LoaderError"),
+    "LoaderFactory": ("text_voice_reader.loaders.factory", "LoaderFactory"),
+    "MarkdownLoader": ("text_voice_reader.loaders.markdown_loader", "MarkdownLoader"),
+    "MsgLoader": ("text_voice_reader.loaders.msg_loader", "MsgLoader"),
+    "PdfLoader": ("text_voice_reader.loaders.pdf_loader", "PdfLoader"),
+    "PptxLoader": ("text_voice_reader.loaders.pptx_loader", "PptxLoader"),
+    "TextLoader": ("text_voice_reader.loaders.base", "TextLoader"),
+    "TvrError": ("text_voice_reader.loaders.base", "TvrError"),
+    "TxtLoader": ("text_voice_reader.loaders.txt_loader", "TxtLoader"),
+    "UnsupportedFormatError": (
+        "text_voice_reader.loaders.base",
+        "UnsupportedFormatError",
+    ),
+    "detect_encoding": ("text_voice_reader.loaders.encoding", "detect_encoding"),
+    "read_text_auto": ("text_voice_reader.loaders.encoding", "read_text_auto"),
+}
+
+
+def __getattr__(name: str) -> Any:
+    if name not in _ATTR_SOURCES:
+        raise AttributeError(name)
+    module_name, attr_name = _ATTR_SOURCES[name]
+    module = import_module(module_name)
+    return getattr(module, attr_name)
```

## src/text_voice_reader/default.toml

```
<new file>
```

```python
# TextVoiceReader default configuration
# This file is the source copy for the packaged default config.
# Runtime loading uses the default.toml bundled inside the Python package.

[app]
theme = "dark"            # "dark" | "light" | "system"
ui_language = "ja"        # "ja" | "en"

[tts]
engine = "sapi5"          # "sapi5" | "onnx"
voice = ""                # empty = use first available. e.g. "Microsoft Haruka Desktop"
rate = 0                  # -10..+10 (SAPI5 scale)
volume = 90               # 0..100
pitch = 0                 # -10..+10  (applied via SSML <prosody pitch>)
use_ssml = true
# Path to ONNX model (used only when engine = "onnx")
onnx_model_path = ""

[output]
play = true               # play audio in-app
save_wav = true           # also save WAV to disk
# Use %USERPROFILE% / ~ style. Resolved at runtime.
save_dir = "~/Documents/TextVoiceReader/out"
wav_sample_rate = 22050   # 22050 or 44100
# Per-sentence temp wav directory (hybrid mode). Empty = system temp.
temp_dir = ""

[processing]
normalize_nfkc = true
strip_urls = true
split_max_chars = 120
skip_empty_lines = true
# Whether to apply heuristic header/footer removal for PDFs
pdf_strip_headers = true

[logging]
level = "INFO"            # DEBUG | INFO | WARNING | ERROR
log_to_file = true
# Rotation: size-based
rotation = "10 MB"
retention = "14 days"

```

## config/default.toml

```diff
--- a/config/default.toml
+++ b/config/default.toml
@@ -1,6 +1,6 @@
 # TextVoiceReader default configuration
-# This file is copied to %APPDATA%/TextVoiceReader/config.toml on first run
-# and loaded/merged on subsequent runs.
+# This file is the source copy for the packaged default config.
+# Runtime loading uses the default.toml bundled inside the Python package.
 
 [app]
 theme = "dark"            # "dark" | "light" | "system"
```

## build/build_exe.py

```diff
--- a/build/build_exe.py
+++ b/build/build_exe.py
@@ -17,7 +17,7 @@
 
 ROOT = Path(__file__).resolve().parent.parent
 ENTRY_SCRIPT = ROOT / "src" / "text_voice_reader" / "__main__.py"
-CONFIG_DIR = ROOT / "config"
+PACKAGED_CONFIG = ROOT / "src" / "text_voice_reader" / "default.toml"
 DIST_DIR = ROOT / "build" / "dist"
 WORK_DIR = ROOT / "build" / "work"
 APP_NAME = "TextVoiceReader"
@@ -43,8 +43,8 @@
         "--distpath", str(DIST_DIR),
         "--workpath", str(WORK_DIR),
         "--specpath", str(WORK_DIR),
-        # Bundle the default config alongside the exe
-        f"--add-data={CONFIG_DIR}{_sep()}config",
+        # Bundle the packaged default config alongside the package.
+        f"--add-data={PACKAGED_CONFIG}{_sep()}text_voice_reader",
         # Collect all submodules of these packages
         "--collect-all", "customtkinter",
         "--collect-all", "langid",
@@ -70,7 +70,7 @@
         "--enable-plugin=tk-inter",
         "--include-package=customtkinter",
         "--include-package=langid",
-        f"--include-data-dir={CONFIG_DIR}=config",
+        f"--include-data-files={PACKAGED_CONFIG}=text_voice_reader/default.toml",
         str(ENTRY_SCRIPT),
     ]
     _run(cmd)
```

## pyproject.toml

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -23,12 +23,10 @@
 dependencies = [
     "pywin32>=306; platform_system == 'Windows'",
     "customtkinter>=5.2.0",
-    "CTkTable>=1.1",
     "loguru>=0.7.0",
     "pydantic>=2.5",
     "pydantic-settings>=2.1",
     "toml>=0.10",
-    "PyYAML>=6.0",
     "pymupdf>=1.24",
     "python-docx>=1.1",
     "python-pptx>=0.6",
@@ -40,9 +38,7 @@
     "unidic-lite>=1.0",
     "langid>=1.1",
     "anyio>=4.0",
-    "tqdm>=4.66",
     "pyperclip>=1.8",
-    "watchdog>=3.0",
 ]
 
 [project.optional-dependencies]
@@ -72,7 +68,7 @@
 where = ["src"]
 
 [tool.setuptools.package-data]
-text_voice_reader = ["../config/default.toml"]
+text_voice_reader = ["default.toml"]
 
 [tool.pytest.ini_options]
 minversion = "7.0"
```

## README.md

```diff
--- a/README.md
+++ b/README.md
@@ -18,7 +18,6 @@
 - **保存モード**: 高品質 WAV ファイルとして書き出し
 - **ハイブリッド**: 再生しながら同じ内容を WAV に保存
 - **音声設定**: Voice / Speed / Volume / Pitch のリアルタイム調整
-- **ドラッグ&ドロップ対応** のモダンな CustomTkinter UI
 - **CLI モード** で自動化（バッチ処理）にも利用可能
 - **loguru** による詳細なログ、**pydantic-settings** による型安全な設定
 
@@ -28,83 +27,90 @@
 
 - Windows 10 / 11 (x64)
 - Python 3.11 以上
-- SAPI5 対応音声パック（Haruka / Ayumi 等の日本語音声は Microsoft Store から追加インストール可能）
+- 日本語音声を使う場合は、Windows 側に日本語 SAPI5 音声がインストールされていること
+
+> 本アプリの本番ターゲットは Windows です。テストや一部処理は他 OS でも動きますが、SAPI5 読み上げは Windows 専用です。
 
 ---
 
 ## インストール
 
-### 開発環境 (pip install -e)
-
-```powershell
-python -m venv .venv
-.venv\Scripts\activate
-pip install -U pip
-pip install -e ".[dev]"
-```
-
-### 実行
-
-GUI:
+### 通常インストール
+
+```powershell
+pip install .
+```
+
+### 開発インストール
+
+```powershell
+pip install -e .[dev]
+```
+
+### 依存ライブラリが不足した場合
+
+```powershell
+pip install -U pywin32 customtkinter loguru pydantic pydantic-settings toml \
+    pymupdf python-docx python-pptx beautifulsoup4 Markdown docx2txt \
+    extract-msg mecab-python3 unidic-lite langid pyperclip
+```
+
+---
+
+## GUI の使い方
+
 ```powershell
 python -m text_voice_reader
 ```
 
-CLI:
-```powershell
-python -m text_voice_reader --file input.md --out output.wav --no-gui
+### 基本フロー
+
+1. **📂 ファイルを開く** または **📋 クリップボード** でテキストを取り込む
+2. 右パネルで **Voice / Speed / Volume / Pitch** を調整
+3. 出力設定で **再生** / **WAV保存** を選ぶ
+4. **▶ 再生** を押す
+5. 必要なら **⏹ 停止** で中断する
+
+> 現在の GUI は **ドラッグ&ドロップ非対応** です。ファイルの読み込みは「📂 ファイルを開く」を使用してください。
+
+---
+
+## CLI の使い方
+
+### ファイルを読み上げ
+
+```powershell
+python -m text_voice_reader --file sample.txt --no-gui
+```
+
+### 再生せず WAV だけ保存
+
+```powershell
+python -m text_voice_reader --file sample.txt --no-gui --no-play
+```
+
+### テキスト直接指定
+
+```powershell
+python -m text_voice_reader --text "こんにちは。これはテストです。" --no-gui
+```
+
+### 利用可能音声の一覧
+
+```powershell
 python -m text_voice_reader --list-voices
 ```
 
-### exe 配布版
-
-```powershell
-python build/build_exe.py --mode pyinstaller
-# 出力: build/dist/TextVoiceReader.exe
-```
-
-Nuitka でビルドする場合:
-```powershell
-python build/build_exe.py --mode nuitka
-```
-
----
-
-## 基本的な使い方
-
-### GUI モード
-
-1. アプリを起動する
-2. **「📂 ファイルを開く」** でテキストファイルを選択
-3. 右パネルで音声・速度・音量・ピッチを調整
-4. **「▶ 再生」** ボタンで読み上げ開始（出力設定に従い WAV も同時保存）
-
-### CLI モード
-
-```powershell
-# 読み上げ + WAV 保存（デフォルト）
-python -m text_voice_reader --file sample.md --no-gui
-
-# WAV 保存のみ（再生なし）
-python -m text_voice_reader --file sample.md --no-gui --no-play --out out.wav
-
-# 直接テキストを指定
-python -m text_voice_reader --text "こんにちは世界" --no-gui
-
-# 声や速度を指定
-python -m text_voice_reader --file a.txt --voice Haruka --rate 2 --volume 85 --no-gui
-
-# 使える音声を一覧表示
-python -m text_voice_reader --list-voices
-```
+CLI 完了時は `success=<件数> failed=<件数> total=<件数>` を標準エラーへ出力します。
+一部失敗を含む場合、終了コードは非 0 になります。
 
 ---
 
 ## 設定ファイル
 
-設定は 3 レイヤーでマージされます（下が優先）:
-
-1. パッケージ同梱の `config/default.toml`
+設定は次の順で読み込まれます（下が優先）:
+
+1. パッケージ同梱のデフォルト設定
 2. ユーザー設定 `%APPDATA%/TextVoiceReader/config.toml`
 3. 環境変数 `TVR_*`（例: `TVR_TTS__VOICE=Haruka`）
 
@@ -179,7 +185,7 @@
 → Windows 設定 → 時刻と言語 → 言語と地域 → 日本語 → オプション → テキスト読み上げをインストール、で Haruka 等が追加されます。
 
 **Q. 一時停止が効かない**
-→ 現実装では文境界でしか一時停止できないため、**「⏹ 停止」→ 再 ▶ 再生** を使ってください。真の一時停止は将来のバージョンで対応予定です。
+→ 現在の GUI は **一時停止ボタンを提供していません**。途中で止める場合は **「⏹ 停止」** を使用してください。
 
 **Q. ONNX モデルは使える？**
 → アーキテクチャ上は対応可能です (`tts.engine = "onnx"` 指定時)。ただし現在はスタブ実装で、モデルの取り込みは Phase 5 の作業項目です。
```

## docs/user_guide.md

```diff
--- a/docs/user_guide.md
+++ b/docs/user_guide.md
@@ -18,7 +18,7 @@
 │                      │  ☑ 再生  ☑ WAV保存             │
 │                      │  保存先: [...] [選択]           │
 ├──────────────────────┴─────────────────────────────────┤
-│ [▶ 再生] [⏸] [⏹]     ████████░░░░ 34/120  あのね、... │
+│ [▶ 再生] [⏹]          ████████░░░░ 34/120  あのね、... │
 ├────────────────────────────────────────────────────────┤
 │ [▾ ログ] 折りたたみ式のログ表示                        │
 └────────────────────────────────────────────────────────┘
@@ -32,6 +32,7 @@
 3. 右パネルで Voice（音声）を選択、Speed/Volume/Pitch を調整
 4. 出力設定（再生 / WAV保存）を確認
 5. **▶ 再生** ボタン
+6. 中断したい場合は **⏹ 停止** を使用
 
 ### クリップボードから読み込む
 1. 他のアプリでテキストをコピー (Ctrl+C)
@@ -69,7 +70,7 @@
 
 | 優先度 | 場所 | 用途 |
 |:------:|-----|------|
-| 低 | `<パッケージ>/config/default.toml` | 同梱デフォルト |
+| 低 | パッケージ同梱の `default.toml` | 同梱デフォルト |
 | 中 | `%APPDATA%\TextVoiceReader\config.toml` | ユーザー設定（GUIで保存可） |
 | 高 | `TVR_*` 環境変数 | CI/バッチ用の上書き |
 
@@ -120,6 +121,9 @@
 }
 ```
 
+CLI 完了時は `success=<件数> failed=<件数> total=<件数>` を標準エラーへ出力します。
+失敗が 1 件でもあれば終了コードは非 0 です。
+
 ## トラブルシューティング
 
 | 症状 | 対処 |
@@ -127,7 +131,7 @@
 | 「SAPI5 is only available on Windows」 | 本アプリは Windows 専用です |
 | 「pywin32 is not installed」 | `pip install pywin32` |
 | 日本語音声が出ない | Windows の言語設定で日本語の「テキスト読み上げ」を追加 |
-| 一時停止が効かない | 現在の実装では文境界のみ。⏹ 停止 → ▶ 再生で対応 |
+| 一時停止したい | 現在は未対応です。⏹ 停止 → ▶ 再生で対応 |
 | 長いPDFで最初の合成が重い | 初回は SAPI5 が音声キャッシュを作るため。2回目以降は高速化 |
 | WAVが途切れる | サンプリングレートを 44100 にしてみる (`output.wav_sample_rate = 44100`) |
 
```

## tests/conftest.py

```
<new file>
```

```python
from __future__ import annotations

import sys
import types


if "markdown" not in sys.modules:
    markdown_mod = types.ModuleType("markdown")
    markdown_mod.markdown = lambda text, **kwargs: text  # type: ignore[attr-defined]
    sys.modules["markdown"] = markdown_mod


if "bs4" not in sys.modules:
    bs4_mod = types.ModuleType("bs4")

    class _DummySoup:
        def __init__(self, html: str, parser: str) -> None:
            self._html = html

        def find_all(self, tags):
            return []

        def get_text(self, separator: str = "") -> str:
            return self._html

    bs4_mod.BeautifulSoup = _DummySoup  # type: ignore[attr-defined]
    sys.modules["bs4"] = bs4_mod

```

## tests/unit/test_orchestrator_run_result.py

```
<new file>
```

```python
from __future__ import annotations

from pathlib import Path

from text_voice_reader.config import AppConfig, OutputSection, ProcessingSection, TtsSection
from text_voice_reader.orchestrator.app_orchestrator import AppOrchestrator
from text_voice_reader.processing.splitter import Sentence
from text_voice_reader.tts.options import SynthesisOptions
from text_voice_reader.utils.threading_utils import StopToken


class _FakeEngine:
    name = "fake"

    def list_voices(self):
        return []

    def synthesize_to_file(self, text: str, wav_path: Path, opts: SynthesisOptions) -> None:
        wav_path.write_bytes(f"WAV:{text}".encode("utf-8"))

    def speak_async(self, text: str, opts: SynthesisOptions):  # pragma: no cover
        raise NotImplementedError


def _make_cfg(tmp_path: Path) -> AppConfig:
    return AppConfig(
        tts=TtsSection(engine="onnx"),
        output=OutputSection(
            play=False,
            save_wav=True,
            save_dir=str(tmp_path),
            wav_sample_rate=22050,
        ),
        processing=ProcessingSection(),
    )


def test_run_result_counts_partial_failures(monkeypatch, tmp_path: Path):
    orch = AppOrchestrator(_make_cfg(tmp_path))
    monkeypatch.setattr(orch, "get_engine", lambda: _FakeEngine())

    sentences = [Sentence(id=0, text="ok"), Sentence(id=1, text="boom")]

    calls: list[str] = []

    class _FakeHybridSink:
        def __init__(self, *args, **kwargs):
            self._save_path = kwargs.get("save_path")

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

        def consume(self, text: str, opts: SynthesisOptions, stop: StopToken) -> None:
            calls.append(text)
            if text == "boom":
                raise RuntimeError("synthetic failure")

    monkeypatch.setattr(
        "text_voice_reader.orchestrator.app_orchestrator.HybridSink",
        _FakeHybridSink,
    )

    result = orch.run(sentences, play=False, save_wav=True, source_name="sample")

    assert calls == ["ok", "boom"]
    assert result.completed == 1
    assert result.failed == 1
    assert result.total_sentences == 2
    assert result.cancelled is False


def test_run_result_preserves_failure_count_on_cancel(monkeypatch, tmp_path: Path):
    orch = AppOrchestrator(_make_cfg(tmp_path))
    monkeypatch.setattr(orch, "get_engine", lambda: _FakeEngine())

    sentences = [Sentence(id=0, text="ok"), Sentence(id=1, text="later")]
    stop = StopToken()

    class _FakeHybridSink:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

        def consume(self, text: str, opts: SynthesisOptions, stop_token: StopToken) -> None:
            stop.set()

    monkeypatch.setattr(
        "text_voice_reader.orchestrator.app_orchestrator.HybridSink",
        _FakeHybridSink,
    )

    result = orch.run(sentences, play=False, save_wav=True, source_name="sample", stop=stop)

    assert result.completed == 1
    assert result.failed == 0
    assert result.cancelled is True

```

## tests/unit/test_app_cli.py

```
<new file>
```

```python
from __future__ import annotations

import argparse
from pathlib import Path

from text_voice_reader.app import _run_cli
from text_voice_reader.config import AppConfig
from text_voice_reader.orchestrator.app_orchestrator import RunResult


class _FakeOrchestrator:
    def __init__(self, cfg: AppConfig, result: RunResult):
        self._result = result

    def load_and_prepare(self, path: Path):
        return [type("Sentence", (), {"text": "hello"})()]

    def prepare_text(self, text: str):
        return [type("Sentence", (), {"text": text or "hello"})()]

    def run(self, *args, **kwargs):
        return self._result

    def get_engine(self):  # pragma: no cover
        raise NotImplementedError


def _args(tmp_path: Path, **overrides):
    data = {
        "list_voices": False,
        "file": None,
        "text": "hello",
        "out": None,
        "voice": None,
        "rate": None,
        "volume": None,
        "pitch": None,
        "no_gui": True,
        "no_play": False,
        "no_save": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_run_cli_returns_nonzero_on_partial_failure(monkeypatch, tmp_path: Path, capsys):
    result = RunResult(
        total_sentences=3,
        completed=2,
        failed=1,
        output_wav=None,
        cancelled=False,
    )
    monkeypatch.setattr(
        "text_voice_reader.app.AppOrchestrator",
        lambda cfg: _FakeOrchestrator(cfg, result),
    )

    code = _run_cli(_args(tmp_path), AppConfig())

    captured = capsys.readouterr()
    assert code == 1
    assert "success=2 failed=1 total=3" in captured.err


def test_run_cli_returns_zero_on_full_success(monkeypatch, tmp_path: Path):
    result = RunResult(
        total_sentences=1,
        completed=1,
        failed=0,
        output_wav=None,
        cancelled=False,
    )
    monkeypatch.setattr(
        "text_voice_reader.app.AppOrchestrator",
        lambda cfg: _FakeOrchestrator(cfg, result),
    )

    code = _run_cli(_args(tmp_path), AppConfig())

    assert code == 0

```

## tests/unit/test_config_paths.py

```
<new file>
```

```python
from __future__ import annotations

from text_voice_reader.config import load_config
from text_voice_reader.utils.paths import get_package_config_path, get_packaged_config_text


def test_packaged_default_config_is_available():
    path = get_package_config_path()
    assert path.is_file()
    assert path.name == "default.toml"


def test_load_config_reads_packaged_default_when_user_file_missing(tmp_path):
    cfg = load_config(user_config_path=tmp_path / "missing.toml")
    packaged = get_packaged_config_text()

    assert "[tts]" in packaged
    assert cfg.tts.engine == "sapi5"
    assert cfg.output.save_wav is True

```

## tests/unit/test_splitter.py

```diff
--- a/tests/unit/test_splitter.py
+++ b/tests/unit/test_splitter.py
@@ -62,3 +62,9 @@
     # The very short "短。" should merge into an adjacent fragment
     for x in out:
         assert x.text != "短"
+
+
+def test_split_keeps_common_english_abbreviations_together():
+    s = SentenceSplitter(SplitterOptions(max_chars=120))
+    out = s.split("Dr. Smith went home. He slept.")
+    assert [x.text for x in out] == ["Dr. Smith went home.", "He slept."]
```
