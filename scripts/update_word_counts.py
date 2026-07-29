#!/usr/bin/env python3
"""Recompute the Notion `Words` property for every page (or one page).

Recomputes from scratch every run — no last_edited_time change detection — and
writes only the pages whose stored value differs, so re-running is idempotent.

    cd ~/arealclimber/brainwave
    PYTHONPATH=. venv/bin/python scripts/update_word_counts.py                  # all pages, write
    PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --dry-run        # all pages, no write
    PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --page <PAGE_ID>
    PYTHONPATH=. venv/bin/python scripts/update_word_counts.py --csv /tmp/r.csv # audit trail

Counting semantics live in notion_service.py: Chinese characters count 1 each,
everything else is tokenized as \\b\\w+\\b, and content after a Readability /
Correctness / Ask AI H1 is excluded (AI_SECTION_HEADINGS).
"""
import argparse
import asyncio
import csv
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

from notion_service import notion_service  # noqa: E402  (needs env loaded first)


def title_of(page: dict) -> str:
    return "".join(
        rt.get("plain_text", "") or rt.get("text", {}).get("content", "")
        for rt in page.get("properties", {}).get("Idea", {}).get("title", [])
    ) or "(untitled)"


def stored_words(page: dict):
    return page.get("properties", {}).get("Words", {}).get("number")


async def process(page: dict, apply: bool, index: str) -> tuple[str, dict]:
    """Returns (outcome, csv_row) where outcome is updated / unchanged / failed."""
    page_id = page["page_id"] if "page_id" in page else page["id"]
    before = stored_words(page)
    row = {
        "page_id": page_id,
        "url": page.get("url", ""),
        "title": title_of(page),
        "stored": before,
        "recomputed": "",
        "error": "",
    }

    try:
        content = await notion_service.get_page_content(page_id)
        counted = notion_service.count_words(content)
        row["recomputed"] = counted
    except Exception as exc:
        row["error"] = str(exc)
        print(f"{index} ERR  {row['title'][:55]} :: {exc}")
        return "failed", row

    if before == counted:
        print(f"{index} ok   {counted:>6}  {row['title'][:55]}")
        return "unchanged", row

    arrow = f"{before if before is not None else '-':>6} -> {counted:<6}"
    if not apply:
        print(f"{index} DIFF {arrow}  {row['title'][:55]}")
        return "updated", row

    if await notion_service.update_word_count(page_id, counted):
        print(f"{index} DIFF {arrow}  {row['title'][:55]}  ✓")
        await asyncio.sleep(0.34)  # Notion's average rate limit is ~3 req/s
        return "updated", row

    row["error"] = "update_word_count failed"
    print(f"{index} DIFF {arrow}  {row['title'][:55]}  ✗")
    return "failed", row


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", help="only this page id")
    parser.add_argument("--dry-run", action="store_true", help="compute but do not write")
    parser.add_argument("--csv", help="write a per-page report to this path")
    args = parser.parse_args()
    apply = not args.dry_run

    if not notion_service.enabled:
        sys.exit("NOTION_TOKEN / NOTION_DATABASE_ID missing (expected in ./.env)")

    if args.page:
        pages = [notion_service.client.pages.retrieve(page_id=args.page)]
    else:
        pages = await notion_service.get_database_pages()
        if not pages:
            sys.exit("no pages returned from the database")

    print(f"pages: {len(pages)}  mode: {'WRITE' if apply else 'DRY RUN'}\n")

    tally = {"updated": 0, "unchanged": 0, "failed": 0}
    rows = []
    for i, page in enumerate(pages, 1):
        outcome, row = await process(page, apply, f"[{i:4}/{len(pages)}]")
        tally[outcome] += 1
        rows.append(row)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nreport: {args.csv}")

    verb = "updated" if apply else "needing update"
    print(
        f"\nsummary: {len(pages)} pages | {tally['updated']} {verb}"
        f" | {tally['unchanged']} already correct | {tally['failed']} failed"
    )
    if not apply and tally["updated"]:
        print("re-run without --dry-run to write these values")


if __name__ == "__main__":
    asyncio.run(main())
