# /// script
# requires-python = ">=3.12"
# dependencies = ["pdfplumber>=0.11", "openpyxl>=3.1"]
# ///
# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Extract transactions from bank exports (canonical CSV, any CSV/XLSX, PDF with tables) into the ledger.

No bank-specific rules: columns are recognised by their content (dates, amounts, free text) and, only where the
content is not enough (e.g. separate debit/credit columns), by generic header keywords.

Usage:
    uv run extract_transactions.py [FILES/DIRS, default data/reports/] [--account NAME] [--dry-run]
"""

import argparse
import csv
import io
import logging
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from ledger import (
    CANONICAL_COLUMNS,
    Transaction,
    default_data_dir,
    detect_currency,
    is_amount,
    is_date,
    merge_into_ledger,
    normalize_text,
    parse_amount,
    parse_date,
    read_transactions,
    write_transactions,
)

SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xlsm", ".pdf"}
COLUMN_RATIO = 0.8

BALANCE_KEYWORDS = ("saldo", "balance")
DEBIT_KEYWORDS = ("dare", "uscit", "addebit", "debit", "withdraw", "spes", "paid")
CREDIT_KEYWORDS = ("avere", "entrat", "accredit", "credit", "deposit", "received")
DESCRIPTION_KEYWORDS = ("descri", "operazion", "causale", "dettagl", "detail", "memo", "payee", "beneficiar")
CATEGORY_KEYWORDS = ("categ",)

Table = list[list[str]]

logger = logging.getLogger("extract_transactions")


class LayoutError(Exception):
    """The table layout cannot be interpreted unambiguously: a human (or Claude) must look at the file."""


@dataclass
class Layout:
    """Which column holds what, for one group of tables sharing the same width."""

    date_col: int
    description_col: int
    amount_col: int | None = None
    debit_col: int | None = None
    credit_col: int | None = None
    category_col: int | None = None
    day_first: bool = True
    header: list[str] = field(default_factory=list)

    def describe(self) -> str:
        """Human readable summary of the detected layout."""

        def name(col: int | None) -> str:
            if col is None:
                return "-"
            label = self.header[col] if col < len(self.header) and self.header[col] else "?"
            return f"#{col} ({label})"

        amount = (
            f"amount={name(self.amount_col)}"
            if self.amount_col is not None
            else f"debit={name(self.debit_col)} credit={name(self.credit_col)}"
        )
        order = "day/month" if self.day_first else "month/day"
        return (
            f"date={name(self.date_col)} [{order}] description={name(self.description_col)} {amount} "
            f"category={name(self.category_col)}"
        )


# ---------------------------------------------------------------------------- readers


def _cell_to_text(value: object) -> str:
    match value:
        case None:
            return ""
        case datetime() | date():
            return value.strftime("%Y-%m-%d")
        case float():
            return f"{value:.2f}" if value != int(value) else str(int(value))
        case _:
            return normalize_text(str(value))


def read_pdf(path: Path) -> list[Table]:
    """Read every table of a PDF; fall back to text alignment when the PDF has no ruling lines."""
    import pdfplumber

    tables: list[Table] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if not any(len(t) > 1 for t in page_tables):
                page_tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
            tables.extend([[_cell_to_text(c) for c in row] for row in t] for t in page_tables)
    return tables


def read_csv(path: Path) -> list[Table]:
    """Read a delimited text file, guessing encoding and delimiter."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text.splitlines()[:200]

    def consistency(delimiter: str) -> int:
        """How many lines share the most common field count (title/footer lines do not disturb it)."""
        widths = Counter(len(r) for r in csv.reader(sample, delimiter=delimiter) if len(r) > 1)
        return widths.most_common(1)[0][1] if widths else 0

    delimiter = max(";\t|,", key=consistency)
    return [[[_cell_to_text(c) for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]]


def read_xlsx(path: Path) -> list[Table]:
    """Read every sheet of an Excel workbook as a table."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [[[_cell_to_text(c) for c in row] for row in sheet.iter_rows(values_only=True)] for sheet in workbook]


def read_tables(path: Path) -> list[Table]:
    """Dispatch on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx(path)
    return read_csv(path)


# ---------------------------------------------------------------------------- layout detection


def _is_data_row(row: list[str]) -> bool:
    return any(is_date(c) for c in row) and any(is_amount(c) for c in row)


def _has_keyword(header: str, keywords: tuple[str, ...]) -> bool:
    words = re.findall(r"[a-zà-ù]+", header.lower())
    return any(w.startswith(k) for w in words for k in keywords)


def _find_header(rows: Table) -> list[str]:
    """The header is the last mostly-filled, date-free row before the first data row."""
    header: list[str] = []
    for row in rows:
        if _is_data_row(row):
            break
        filled = [c for c in row if c]
        if len(filled) >= max(2, len(row) // 2) and not any(is_date(c) for c in row):
            header = [c.lower() for c in row]
    return header


def detect_layout(rows: Table) -> Layout:
    """
    Infer the meaning of each column from the content of the data rows.

    Raises:
        LayoutError: when the content does not allow an unambiguous interpretation
    """
    data = [r for r in rows if _is_data_row(r)]
    width = len(rows[0])
    header = (_find_header(rows) + [""] * width)[:width]

    def ratio(col: int, predicate: Callable[[str], bool]) -> float:
        cells = [r[col] for r in data if r[col]]
        return sum(1 for c in cells if predicate(c)) / len(cells) if cells else 0.0

    date_cols = [c for c in range(width) if ratio(c, is_date) >= COLUMN_RATIO]
    amount_cols = [
        c
        for c in range(width)
        if c not in date_cols and ratio(c, is_amount) >= COLUMN_RATIO and not _has_keyword(header[c], BALANCE_KEYWORDS)
    ]
    text_cols = [c for c in range(width) if c not in date_cols and c not in amount_cols]
    if not date_cols or not amount_cols or not text_cols:
        raise LayoutError(f"cannot find date/amount/description columns (header: {header})")

    layout = Layout(date_col=date_cols[0], description_col=-1, header=header)
    if len(amount_cols) == 1:
        layout.amount_col = amount_cols[0]
    elif len(amount_cols) == 2:
        debit = [c for c in amount_cols if _has_keyword(header[c], DEBIT_KEYWORDS)]
        credit = [c for c in amount_cols if _has_keyword(header[c], CREDIT_KEYWORDS)]
        if len(debit) != 1 or len(credit) != 1 or debit == credit:
            raise LayoutError(f"two amount columns but cannot tell debit from credit (header: {header})")
        layout.debit_col, layout.credit_col = debit[0], credit[0]
    else:
        raise LayoutError(f"{len(amount_cols)} amount-like columns, cannot choose (header: {header})")

    category = [c for c in text_cols if _has_keyword(header[c], CATEGORY_KEYWORDS)]
    layout.category_col = category[0] if category else None
    candidates = [c for c in text_cols if c != layout.category_col]
    named = [c for c in candidates if _has_keyword(header[c], DESCRIPTION_KEYWORDS)]

    def avg_length(col: int) -> float:
        return sum(len(r[col]) for r in data) / len(data)

    layout.description_col = named[0] if named else max(candidates, key=avg_length)

    first_parts = [int(m[1]) for r in data if (m := re.match(r"^(\d{1,2})[./-](\d{1,2})", r[layout.date_col]))]
    second_parts = [int(m[2]) for r in data if (m := re.match(r"^(\d{1,2})[./-](\d{1,2})", r[layout.date_col]))]
    layout.day_first = not (any(p > 12 for p in second_parts) and not any(p > 12 for p in first_parts))
    return layout


def _row_amount(row: list[str], layout: Layout) -> Decimal | None:
    if layout.amount_col is not None:
        cell = row[layout.amount_col]
        return parse_amount(cell) if is_amount(cell) else None
    debit_cell, credit_cell = row[layout.debit_col or 0], row[layout.credit_col or 0]
    if is_amount(debit_cell) and parse_amount(debit_cell) != 0:
        return -abs(parse_amount(debit_cell))
    if is_amount(credit_cell):
        return abs(parse_amount(credit_cell))
    return None


def tables_to_transactions(
    tables: list[Table], source_file: str, account: str = "", default_currency: str = "EUR"
) -> tuple[list[Transaction], list[str]]:
    """
    Convert raw tables into transactions. Tables with the same width are treated as one table split across pages.

    Returns:
        The transactions and a description of the layouts that were used
    """
    groups: dict[int, Table] = {}
    for table in tables:
        for row in table:
            if any(row):
                groups.setdefault(len(row), []).append(row)

    transactions: list[Transaction] = []
    layouts: list[str] = []
    errors: list[str] = []
    for rows in groups.values():
        if not any(_is_data_row(r) for r in rows):
            continue
        try:
            layout = detect_layout(rows)
        except LayoutError as e:
            errors.append(str(e))
            continue
        layouts.append(layout.describe())
        for row in rows:
            if not is_date(row[layout.date_col]) or (amount := _row_amount(row, layout)) is None:
                continue
            currency_cell = row[layout.amount_col] if layout.amount_col is not None else " ".join(row)
            transactions.append(
                Transaction(
                    date=parse_date(row[layout.date_col], layout.day_first),
                    description=normalize_text(row[layout.description_col]),
                    amount=amount,
                    currency=detect_currency(currency_cell) or default_currency,
                    category=normalize_text(row[layout.category_col]) if layout.category_col is not None else "",
                    account=account,
                    source_file=source_file,
                )
            )
    if not transactions and errors:
        raise LayoutError("; ".join(errors))
    return transactions, layouts


def is_canonical_csv(path: Path) -> bool:
    """Level 0: the file already uses the canonical columns."""
    if path.suffix.lower() != ".csv":
        return False
    with path.open(encoding="utf-8-sig") as handle:
        header = handle.readline().strip().split(",")
    return {"date", "description", "amount"} <= set(header) and set(header) <= set(CANONICAL_COLUMNS)


def extract_file(path: Path, account: str, currency: str) -> tuple[list[Transaction], str]:
    """Extract the transactions of one file, returning them with a description of how they were read."""
    if is_canonical_csv(path):
        transactions = read_transactions(path)
        for tx in transactions:
            tx.source_file = tx.source_file or path.name
            tx.account = tx.account or account
        return transactions, "canonical CSV"
    transactions, layouts = tables_to_transactions(read_tables(path), path.name, account, currency)
    return transactions, " | ".join(layouts)


# ---------------------------------------------------------------------------- CLI


def _expand(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            files.extend(sorted(p for p in item.iterdir() if p.suffix.lower() in SUPPORTED_SUFFIXES))
        else:
            files.append(item)
    return files


def _summary(transactions: list[Transaction]) -> str:
    income = sum((t.amount for t in transactions if t.amount > 0), Decimal(0))
    expense = sum((t.amount for t in transactions if t.amount < 0), Decimal(0))
    first, last = min(t.date for t in transactions), max(t.date for t in transactions)
    return (
        f"{len(transactions)} transactions from {first} to {last}; "
        f"income {income:.2f}, expenses {expense:.2f}, net {income + expense:.2f}"
    )


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="*", type=Path, help="files or directories (default: <data>/reports/)")
    parser.add_argument("--ledger", type=Path, default=default_data_dir() / "ledger.csv")
    parser.add_argument("--account", default="", help="label of the account/card the files refer to")
    parser.add_argument("--currency", default="EUR", help="currency when the file does not state it")
    parser.add_argument("--dry-run", action="store_true", help="show what would be imported without saving")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    ledger = read_transactions(args.ledger)
    failures = 0
    for path in _expand(args.inputs or [default_data_dir() / "reports"]):
        try:
            transactions, how = extract_file(path, args.account, args.currency)
        except (LayoutError, ValueError, OSError) as e:
            logger.error(f"[FAIL] {path.name}: {e}")
            failures += 1
            continue
        if not transactions:
            logger.error(f"[FAIL] {path.name}: no transactions found (scanned or unstructured document?)")
            failures += 1
            continue
        ledger, added = merge_into_ledger(ledger, transactions)
        logger.info(f"[OK] {path.name}: {_summary(transactions)}")
        logger.info(f"     layout: {how}")
        logger.info(f"     added to ledger: {added} (duplicates skipped: {len(transactions) - added})")

    if not args.dry_run:
        write_transactions(args.ledger, ledger)
        logger.info(f"Ledger {args.ledger}: {len(ledger)} transactions")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
