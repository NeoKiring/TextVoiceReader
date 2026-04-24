"""Spike: read recent Outlook Inbox messages via classic Outlook COM.

This script is intentionally standalone and is not wired into TextVoiceReader yet.
Use it to verify whether the local Windows + classic Outlook environment can be
read safely through pywin32 before implementing the production integration.

What it checks:
    * pywin32 / pythoncom import availability
    * COM initialization on the current thread
    * classic Outlook COM connection
    * Inbox access through the MAPI namespace
    * Recent MailItem extraction into plain Python dataclasses
    * Safe skipping of MeetingItem / ReportItem / other non-MailItem objects

Privacy note:
    This script prints only to the local console. It does not send message data to
    any external service and does not modify Outlook items by default.
"""

from __future__ import annotations

import argparse
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any, Iterator

OUTLOOK_FOLDER_INBOX = 6
OUTLOOK_CLASS_MAIL_ITEM = 43


@dataclass(frozen=True)
class MailSnapshot:
    """Plain Python snapshot of an Outlook MailItem.

    COM objects must not escape the extraction scope. This dataclass is the safe
    boundary for future TextVoiceReader integration work.
    """

    entry_id: str
    subject: str
    sender_name: str
    sender_email: str | None
    received_at: str
    unread: bool
    body_preview: str


class OutlookSpikeError(RuntimeError):
    """Raised when this spike cannot continue due to environment/setup issues."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read recent messages from classic Outlook Inbox via COM. "
            "Run on Windows with pywin32 installed."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of MailItem messages to display. Default: 5.",
    )
    parser.add_argument(
        "--max-scan",
        type=int,
        default=50,
        help=(
            "Maximum Inbox items to inspect while skipping non-MailItem objects. "
            "Default: 50."
        ),
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=160,
        help="Maximum body preview characters printed per message. Default: 160.",
    )
    parser.add_argument(
        "--unread-only",
        action="store_true",
        help="Display only unread MailItem messages.",
    )
    parser.add_argument(
        "--allow-start-outlook",
        action="store_true",
        help=(
            "Allow COM Dispatch to start classic Outlook if no running instance is found. "
            "By default this script only attaches to a running Outlook instance."
        ),
    )
    parser.add_argument(
        "--no-body-preview",
        action="store_true",
        help="Do not print message body previews. Useful for privacy-sensitive checks.",
    )
    return parser.parse_args()


def require_windows() -> None:
    if not sys.platform.startswith("win"):
        raise OutlookSpikeError("This spike requires Windows because Outlook COM is Windows-only.")


def require_pywin32() -> tuple[Any, Any]:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OutlookSpikeError(
            "pywin32 is not installed or could not be imported. "
            "Install it in the active environment with: pip install pywin32"
        ) from exc
    return pythoncom, win32com.client


@contextmanager
def com_scope(pythoncom: Any) -> Iterator[None]:
    """Initialize COM for the current thread and always uninitialize it."""
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def connect_outlook(win32_client: Any, *, allow_start_outlook: bool) -> Any:
    """Return a classic Outlook Application COM object.

    The default path uses GetActiveObject so that this spike can explicitly report
    the "Outlook is not running" case. Pass --allow-start-outlook to permit
    Dispatch("Outlook.Application") to start Outlook.
    """
    try:
        return win32_client.GetActiveObject("Outlook.Application")
    except Exception as active_exc:
        if not allow_start_outlook:
            raise OutlookSpikeError(
                "Could not attach to a running classic Outlook instance. "
                "Start classic Outlook and retry, or pass --allow-start-outlook "
                "to let COM attempt to start it."
            ) from active_exc

    try:
        return win32_client.Dispatch("Outlook.Application")
    except Exception as dispatch_exc:
        raise OutlookSpikeError(
            "Could not create/connect to classic Outlook via COM. "
            "Confirm that classic Outlook for Windows is installed and configured."
        ) from dispatch_exc


def safe_get(obj: Any, attr_name: str, default: Any = "") -> Any:
    try:
        value = getattr(obj, attr_name)
    except Exception:
        return default
    return default if value is None else value


def safe_call(func: Any, default: Any = "") -> Any:
    try:
        value = func()
    except Exception:
        return default
    return default if value is None else value


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sanitize_body_preview(text: str, *, max_chars: int) -> str:
    """Return a compact local-only preview suitable for manual verification."""
    if not text or max_chars <= 0:
        return ""

    # Keep this deliberately simple for the spike. Production sanitizing should
    # live in integrations/outlook/sanitizer.py and receive unit tests.
    text = unescape(text)
    text = re.sub(r"https?://\S+", "URL", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_whitespace(text)

    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def to_received_at_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def extract_sender_email(mail_item: Any) -> str | None:
    """Best-effort sender email extraction without failing the whole spike."""
    sender_email = str(safe_get(mail_item, "SenderEmailAddress", "") or "").strip()

    # Exchange accounts often expose an X.500-style address through
    # SenderEmailAddress. Try PrimarySmtpAddress when available.
    sender = safe_get(mail_item, "Sender", None)
    if sender is not None:
        exchange_user = safe_call(getattr(sender, "GetExchangeUser", lambda: None), None)
        primary_smtp = str(safe_get(exchange_user, "PrimarySmtpAddress", "") or "").strip()
        if primary_smtp:
            return primary_smtp

    return sender_email or None


def extract_mail_snapshot(
    mail_item: Any,
    *,
    preview_chars: int,
    include_body_preview: bool,
) -> MailSnapshot:
    entry_id = str(safe_get(mail_item, "EntryID", "") or "")
    subject = normalize_whitespace(str(safe_get(mail_item, "Subject", "") or ""))
    sender_name = normalize_whitespace(str(safe_get(mail_item, "SenderName", "") or ""))
    sender_email = extract_sender_email(mail_item)
    received_at = to_received_at_text(safe_get(mail_item, "ReceivedTime", ""))
    unread = bool(safe_get(mail_item, "UnRead", False))

    body_preview = ""
    if include_body_preview:
        body = str(safe_get(mail_item, "Body", "") or "")
        body_preview = sanitize_body_preview(body, max_chars=preview_chars)

    return MailSnapshot(
        entry_id=entry_id,
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email,
        received_at=received_at,
        unread=unread,
        body_preview=body_preview,
    )


def iter_recent_mail_snapshots(
    inbox: Any,
    *,
    limit: int,
    max_scan: int,
    unread_only: bool,
    preview_chars: int,
    include_body_preview: bool,
) -> tuple[list[MailSnapshot], int, int]:
    """Return recent MailItem snapshots plus inspected/skipped counts."""
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)

    snapshots: list[MailSnapshot] = []
    inspected_count = 0
    skipped_non_mail_count = 0

    item_count = int(safe_get(items, "Count", 0) or 0)
    scan_count = min(item_count, max_scan)

    for index in range(1, scan_count + 1):
        inspected_count += 1
        item = items.Item(index)
        item_class = safe_get(item, "Class", None)
        if item_class != OUTLOOK_CLASS_MAIL_ITEM:
            skipped_non_mail_count += 1
            continue

        if unread_only and not bool(safe_get(item, "UnRead", False)):
            continue

        snapshots.append(
            extract_mail_snapshot(
                item,
                preview_chars=preview_chars,
                include_body_preview=include_body_preview,
            )
        )
        if len(snapshots) >= limit:
            break

    return snapshots, inspected_count, skipped_non_mail_count


def print_summary(
    snapshots: list[MailSnapshot],
    *,
    inspected_count: int,
    skipped_non_mail_count: int,
    include_body_preview: bool,
) -> None:
    print("Outlook Inbox spike result")
    print("==========================")
    print(f"MailItem snapshots: {len(snapshots)}")
    print(f"Inspected Inbox items: {inspected_count}")
    print(f"Skipped non-MailItem items: {skipped_non_mail_count}")
    print()

    for number, snapshot in enumerate(snapshots, start=1):
        print(f"[{number}]")
        print(f"  received_at : {snapshot.received_at}")
        print(f"  unread      : {snapshot.unread}")
        print(f"  sender_name : {snapshot.sender_name}")
        print(f"  sender_email: {snapshot.sender_email or ''}")
        print(f"  subject     : {snapshot.subject}")
        print(f"  entry_id    : {snapshot.entry_id[:24]}{'…' if snapshot.entry_id else ''}")
        if include_body_preview:
            print(f"  body_preview: {snapshot.body_preview}")
        else:
            print("  body_preview: <disabled>")
        print()


def main() -> int:
    args = parse_args()

    if args.limit < 1:
        print("ERROR: --limit must be >= 1", file=sys.stderr)
        return 2
    if args.max_scan < 1:
        print("ERROR: --max-scan must be >= 1", file=sys.stderr)
        return 2
    if args.preview_chars < 0:
        print("ERROR: --preview-chars must be >= 0", file=sys.stderr)
        return 2

    try:
        require_windows()
        pythoncom, win32_client = require_pywin32()
        with com_scope(pythoncom):
            outlook = connect_outlook(win32_client, allow_start_outlook=args.allow_start_outlook)
            namespace = outlook.GetNamespace("MAPI")
            inbox = namespace.GetDefaultFolder(OUTLOOK_FOLDER_INBOX)
            snapshots, inspected_count, skipped_non_mail_count = iter_recent_mail_snapshots(
                inbox,
                limit=args.limit,
                max_scan=args.max_scan,
                unread_only=args.unread_only,
                preview_chars=args.preview_chars,
                include_body_preview=not args.no_body_preview,
            )
    except OutlookSpikeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Unexpected Outlook COM spike failure: {exc}", file=sys.stderr)
        return 1

    print_summary(
        snapshots,
        inspected_count=inspected_count,
        skipped_non_mail_count=skipped_non_mail_count,
        include_body_preview=not args.no_body_preview,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
