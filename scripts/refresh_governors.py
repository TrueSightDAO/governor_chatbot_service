#!/usr/bin/env python3
"""Refresh governors.json from the TrueSight DAO Main Ledger.

Reads the **Contributors contact information** tab (or a dedicated **Governors** tab)
from the Main Ledger spreadsheet and writes a canonical `governors.json`.

Intended to run inside a GitHub Actions workflow (`.github/workflows/refresh-governors.yml`).
Can also run locally with a service-account JSON.

Usage::

    python3 scripts/refresh_governors.py \
      --credentials /path/to/google_credentials.json \
      --spreadsheet 1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU \
      --sheet-tab "Contributors contact information" \
      --output governors.json

Environment (GitHub Actions)::

    GOOGLE_CREDENTIALS_JSON  — service-account JSON string (inline)
    GOVERNORS_SPREADSHEET_ID — spreadsheet ID (default: Main Ledger)
    GOVERNORS_SHEET_TAB      — tab name (default: "Contributors contact information")
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
DEFAULT_SHEET_TAB = "Contributors contact information"

# Columns we expect in the sheet (0-indexed).  Adjust if schema changes.
# The "Contributors contact information" tab has:
#   A = Name, B = Email, C = Public Key (SPKI base64), D = Status, ...
# We treat a row as a governor if:
#   - Column C (Public Key) is non-empty
#   - Column D (Status) == "Governor"  (or we scan for a Governor marker)
COL_NAME = 0        # A
COL_EMAIL = 1       # B
COL_PUBLIC_KEY = 2  # C
COL_STATUS = 3      # D


def _get_service_account_credentials(credentials_path: str | None = None) -> dict:
    """Load Google service-account JSON from file or env var."""
    env_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if env_json:
        return json.loads(env_json)
    if credentials_path and Path(credentials_path).exists():
        return json.loads(Path(credentials_path).read_text())
    raise RuntimeError(
        "No Google credentials found. Provide --credentials or set GOOGLE_CREDENTIALS_JSON."
    )


def _build_governors_from_sheet(
    spreadsheet_id: str,
    sheet_tab: str,
    credentials: dict,
) -> list[dict]:
    """Fetch rows from the sheet and filter for governors."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "google-auth and google-api-python-client required. "
            "Install: pip install google-auth google-api-python-client"
        ) from exc

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = service_account.Credentials.from_service_account_info(credentials, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)

    # Read the full tab
    range_name = f"{sheet_tab}!A1:Z"
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()
    rows = result.get("values", [])

    if not rows:
        return []

    governors: list[dict] = []
    for i, row in enumerate(rows[1:], start=2):  # skip header
        public_key = row[COL_PUBLIC_KEY].strip() if len(row) > COL_PUBLIC_KEY else ""
        status = row[COL_STATUS].strip() if len(row) > COL_STATUS else ""
        name = row[COL_NAME].strip() if len(row) > COL_NAME else ""
        email = row[COL_EMAIL].strip() if len(row) > COL_EMAIL else ""

        if not public_key:
            continue

        # Accept if status explicitly says "Governor" or if no status column
        is_governor = status.lower() == "governor" if status else True
        if not is_governor:
            continue

        governors.append({
            "public_key": public_key,
            "name": name,
            "email": email,
            "status": status or "Governor",
            "sheet_row": i,
        })

    return governors


def _build_fallback_governors() -> list[dict]:
    """Return an empty list or a hardcoded fallback for dev."""
    return []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Refresh governors.json from Main Ledger.")
    p.add_argument(
        "--credentials",
        default=None,
        help="Path to Google service-account JSON file.",
    )
    p.add_argument(
        "--spreadsheet",
        default=os.getenv("GOVERNORS_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID),
        help="Google Sheets spreadsheet ID.",
    )
    p.add_argument(
        "--sheet-tab",
        default=os.getenv("GOVERNORS_SHEET_TAB", DEFAULT_SHEET_TAB),
        help="Tab name inside the spreadsheet.",
    )
    p.add_argument(
        "--output",
        default="governors.json",
        help="Output JSON file path.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON to stdout; do not write file.",
    )
    p.add_argument(
        "--fallback-only",
        action="store_true",
        help="Skip sheet read; write empty/fallback governors.json.",
    )
    args = p.parse_args(argv)

    if args.fallback_only:
        governors = _build_fallback_governors()
    else:
        try:
            credentials = _get_service_account_credentials(args.credentials)
            governors = _build_governors_from_sheet(
                args.spreadsheet,
                args.sheet_tab,
                credentials,
            )
            print(f"Found {len(governors)} governor(s) from sheet '{args.sheet_tab}'.")
        except Exception as exc:
            print(f"ERROR reading sheet: {exc}", file=sys.stderr)
            print("Falling back to empty governors list.", file=sys.stderr)
            governors = _build_fallback_governors()

    payload = {
        "version": 1,
        "updated_at": _now_iso(),
        "source": args.sheet_tab,
        "spreadsheet_id": args.spreadsheet,
        "governors": governors,
    }

    json_text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.dry_run:
        print(json_text)
        return 0

    output_path = Path(args.output)
    output_path.write_text(json_text, encoding="utf-8")
    print(f"Wrote {len(governors)} governor(s) to {output_path}")
    return 0


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
