# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Canonical transaction model, value parsers and the ledger (the single CSV that holds every transaction).
"""

import csv
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA_DIR_ENV = "FAMILY_BUDGET_DATA"
CANONICAL_COLUMNS = ["date", "description", "amount", "currency", "category", "account", "source_file"]

_DATE_PATTERNS = [
    re.compile(r"^(?P<a>\d{1,2})[./-](?P<b>\d{1,2})[./-](?P<y>\d{4}|\d{2})$"),
]
_ISO_DATE = re.compile(r"^(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})(?:[ T].*)?$")
_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
_CURRENCY_CODES = re.compile(r"\b(EUR|USD|GBP|CHF)\b", re.IGNORECASE)
_AMOUNT = re.compile(r"^[+-]?\d{1,3}(?:[.,' ]?\d{3})*(?:[.,]\d{1,2})?$|^[+-]?\d+(?:[.,]\d{1,2})?$")


@dataclass
class Transaction:
    """A single movement of money. Negative amount = expense, positive = income."""

    date: date
    description: str
    amount: Decimal
    currency: str = "EUR"
    category: str = ""
    account: str = ""
    source_file: str = ""

    def dedup_key(self) -> tuple[str, str, str]:
        """Key used to recognise the same transaction coming from overlapping reports."""
        return (self.date.isoformat(), str(self.amount), normalize_text(self.description).lower())


def default_data_dir() -> Path:
    """Private data directory: $FAMILY_BUDGET_DATA or ./data in the current working directory."""
    return Path(os.environ.get(DATA_DIR_ENV, "data"))


def normalize_text(value: str) -> str:
    """Collapse whitespace and line breaks (multi-line PDF cells) into single spaces."""
    return re.sub(r"\s+", " ", value or "").strip()


def is_date(value: str) -> bool:
    """Return True when the cell looks like a date in one of the supported formats."""
    value = value.strip()
    return bool(_ISO_DATE.match(value) or any(p.match(value) for p in _DATE_PATTERNS))


def parse_date(value: str, day_first: bool = True) -> date:
    """
    Parse a date cell.

    Args:
        value: Text such as "31.10.2026", "31/10/26", "10/31/2026" or "2026-10-31"
        day_first: Interpret "a/b/yyyy" as day/month (European) when True, month/day when False

    Returns:
        The parsed date
    """
    value = value.strip()
    if match := _ISO_DATE.match(value):
        return date(int(match["y"]), int(match["m"]), int(match["d"]))
    for pattern in _DATE_PATTERNS:
        if match := pattern.match(value):
            a, b, year = int(match["a"]), int(match["b"]), int(match["y"])
            year = year + 2000 if year < 100 else year
            day, month = (a, b) if day_first else (b, a)
            return date(year, month, day)
    raise ValueError(f"Unrecognised date: {value!r}")


def _strip_currency(value: str) -> str:
    value = _CURRENCY_CODES.sub("", value)
    for symbol in _CURRENCY_SYMBOLS:
        value = value.replace(symbol, "")
    return re.sub(r"\s+", "", value)


def is_amount(value: str) -> bool:
    """Return True when the cell looks like a monetary amount (and not like a date)."""
    if not value.strip() or is_date(value):
        return False
    return bool(_AMOUNT.match(_strip_currency(value)))


def detect_currency(value: str) -> str | None:
    """Return the ISO currency code written in the cell, if any."""
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in value:
            return code
    match = _CURRENCY_CODES.search(value)
    return match.group(1).upper() if match else None


def parse_amount(value: str) -> Decimal:
    """
    Parse an amount written with either European or Anglo-Saxon separators.

    The last "," or "." followed by one or two digits is the decimal separator; any other separator is a
    thousands separator. Examples: "€ -1.234,56" -> -1234.56, "1,234.56" -> 1234.56, "1.234" -> 1234.
    """
    text = _strip_currency(value).replace("'", "")
    if match := re.search(r"[.,](\d{1,2})$", text):
        integer_part = re.sub(r"[.,]", "", text[: match.start()])
        text = f"{integer_part}.{match.group(1)}"
    else:
        text = re.sub(r"[.,]", "", text)
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as e:
        raise ValueError(f"Unrecognised amount: {value!r}") from e


def write_transactions(path: Path, transactions: list[Transaction]) -> None:
    """Write transactions to a canonical CSV, sorted by date."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_COLUMNS)
        writer.writeheader()
        for tx in sorted(transactions, key=lambda t: (t.date, t.description)):
            row = asdict(tx)
            row["date"] = tx.date.isoformat()
            row["amount"] = f"{tx.amount:.2f}"
            writer.writerow(row)


def read_transactions(path: Path) -> list[Transaction]:
    """Read a canonical CSV (the ledger, or a file already in the canonical format)."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"date", "description", "amount"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is not a canonical CSV, missing columns: {sorted(missing)}")
        result = []
        for row in reader:
            result.append(
                Transaction(
                    date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                    description=row["description"] or "",
                    amount=Decimal(row["amount"]).quantize(Decimal("0.01")),
                    currency=row.get("currency") or "EUR",
                    category=row.get("category") or "",
                    account=row.get("account") or "",
                    source_file=row.get("source_file") or "",
                )
            )
        return result


def find_transaction(ledger: list[Transaction], day: date, amount: Decimal, match: str = "") -> Transaction:
    """
    Find exactly one transaction by date and signed amount, optionally narrowed by a text in its description.

    Raises:
        LookupError: when no transaction or more than one (with different descriptions) matches
    """
    found = [
        t
        for t in ledger
        if t.date == day and t.amount == amount and match.lower() in normalize_text(t.description).lower()
    ]
    if not found:
        raise LookupError(f"No transaction on {day} for {amount} matching {match!r}")
    if len({t.dedup_key() for t in found}) > 1:
        options = "; ".join(t.description for t in found)
        raise LookupError(f"Several transactions on {day} for {amount}: {options}. Use --match to choose.")
    return found[0]


REVERSAL_KEYWORDS = re.compile(r"storn|rimbors|refund|reversal|chargeback|annull", re.IGNORECASE)
REVERSAL_WINDOW_DAYS = 60


def is_reversal(tx: Transaction) -> bool:
    """A reversal/refund: money coming back, recognised by generic keywords in category or description."""
    return tx.amount > 0 and bool(REVERSAL_KEYWORDS.search(f"{tx.category} {tx.description}"))


def cancel_reversals(
    transactions: list[Transaction],
) -> tuple[list[Transaction], list[tuple[Transaction, Transaction]]]:
    """
    Remove reversals together with the payment they cancel.

    A reversal cancels the closest earlier (or same-day) expense of exactly the opposite amount within
    REVERSAL_WINDOW_DAYS. A reversal without a matching payment is kept as a normal transaction.

    Returns:
        The remaining transactions and the cancelled (payment, reversal) pairs
    """
    used: set[int] = set()
    pairs: list[tuple[Transaction, Transaction]] = []
    for r_index, reversal in sorted(enumerate(transactions), key=lambda it: it[1].date):
        if not is_reversal(reversal):
            continue
        candidates = [
            (i, tx)
            for i, tx in enumerate(transactions)
            if i not in used
            and tx.amount == -reversal.amount
            and 0 <= (reversal.date - tx.date).days <= REVERSAL_WINDOW_DAYS
        ]
        if candidates:
            index, payment = max(candidates, key=lambda it: it[1].date)
            used.update({index, r_index})
            pairs.append((payment, reversal))
    return [tx for i, tx in enumerate(transactions) if i not in used], pairs


def merge_into_ledger(ledger: list[Transaction], incoming: list[Transaction]) -> tuple[list[Transaction], int]:
    """
    Merge transactions coming from one source file into the ledger without double counting.

    Identical transactions can legitimately repeat (two identical top-ups on the same day), so the merge works
    on counts: for every key the ledger keeps max(count already present, count in the new file).

    Returns:
        The merged ledger and the number of transactions actually added
    """
    present = Counter(tx.dedup_key() for tx in ledger)
    seen: Counter[tuple[str, str, str]] = Counter()
    merged = list(ledger)
    added = 0
    for tx in incoming:
        key = tx.dedup_key()
        seen[key] += 1
        if seen[key] > present[key]:
            merged.append(tx)
            added += 1
    return merged, added
