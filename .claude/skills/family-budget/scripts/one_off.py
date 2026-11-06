# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Extraordinary (one-off) expenses: transactions the user marks as not part of the ordinary monthly spending.

They live in the private file data/one_off.csv with columns:

    date,amount,description,note

date, amount and description identify the transaction exactly as in the ledger; note explains what it was.
The report lists them in a dedicated table; elsewhere they stay in their categories like any other expense.

Usage:
    uv run one_off.py list [--month 2026-10]
    uv run one_off.py add --date 2026-03-16 --amount -250.00 --note "New washing machine" [--match esempio]
    uv run one_off.py remove --date 2026-03-16 --amount -250.00
"""

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from ledger import Transaction, default_data_dir, find_transaction, normalize_text, read_transactions

ONE_OFF_FILE = "one_off.csv"
COLUMNS = ["date", "amount", "description", "note"]


@dataclass
class OneOff:
    """An expense the user considers extraordinary."""

    date: date
    amount: Decimal
    description: str
    note: str = ""

    def key(self) -> tuple[str, str, str]:
        """Same key as Transaction.dedup_key, to find the transaction it refers to."""
        return (self.date.isoformat(), str(self.amount), normalize_text(self.description).lower())


def load_one_offs(data_dir: Path) -> list[OneOff]:
    """Read data/one_off.csv; a missing file means no extraordinary expenses."""
    path = data_dir / ONE_OFF_FILE
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            OneOff(
                date=date.fromisoformat(row["date"]),
                amount=Decimal(row["amount"]).quantize(Decimal("0.01")),
                description=row.get("description") or "",
                note=row.get("note") or "",
            )
            for row in csv.DictReader(handle)
            if (row.get("date") or "").strip()
        ]


def save_one_offs(data_dir: Path, one_offs: list[OneOff]) -> None:
    """Write data/one_off.csv sorted by date."""
    path = data_dir / ONE_OFF_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for item in sorted(one_offs, key=lambda o: o.date):
            row = asdict(item)
            row["date"] = item.date.isoformat()
            row["amount"] = f"{item.amount:.2f}"
            writer.writerow(row)


def one_off_notes(data_dir: Path) -> dict[tuple[str, str, str], str]:
    """Map transaction keys to the note of the extraordinary expense."""
    return {o.key(): o.note or "una tantum" for o in load_one_offs(data_dir)}


def note_for(tx: Transaction, notes: dict[tuple[str, str, str], str]) -> str | None:
    """Return the note when the transaction is extraordinary, None otherwise."""
    return notes.get(tx.dedup_key())


def main() -> int:
    """List, add and remove extraordinary expenses."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    commands = parser.add_subparsers(dest="command")
    list_cmd = commands.add_parser("list", help="list extraordinary expenses (default command)")
    list_cmd.add_argument("--month", help="restrict to a month, format YYYY-MM")
    add = commands.add_parser("add", help="mark a ledger transaction as extraordinary")
    remove = commands.add_parser("remove", help="mark a transaction as ordinary again")
    for cmd in (add, remove):
        cmd.add_argument("--date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
        cmd.add_argument("--amount", required=True, type=Decimal, help="signed, e.g. -250.00")
        cmd.add_argument("--match", default="", help="text of the description, when several transactions match")
    add.add_argument("--note", required=True, help="what it was, in the user's words")
    args = parser.parse_args()

    items = load_one_offs(args.data_dir)
    if args.command in ("add", "remove"):
        tx = find_transaction(read_transactions(args.data_dir / "ledger.csv"), args.date, args.amount, args.match)
        key = tx.dedup_key()
        if args.command == "add":
            if any(o.key() == key for o in items):
                print(f"Already extraordinary: {tx.date} {tx.amount} {tx.description}")
                return 0
            items.append(OneOff(tx.date, tx.amount, tx.description, args.note))
        else:
            items = [o for o in items if o.key() != key]
        save_one_offs(args.data_dir, items)
        print(f"{'Added' if args.command == 'add' else 'Removed'}: {tx.date} {tx.amount} {tx.description}")
        return 0

    month = getattr(args, "month", None)
    selected = [o for o in items if not month or o.date.strftime("%Y-%m") == month]
    for o in selected:
        print(f"{o.date}  {o.amount:.2f}  {o.description}  ({o.note})")
    print(f"\n{len(selected)} extraordinary expenses, total {sum((o.amount for o in selected), Decimal(0)):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
