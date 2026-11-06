# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Anomalies to verify: transactions the user does not recognise or wants to check.

They live in the private file data/anomalies.csv with columns:

    date,amount,description,question,status,resolution

- date, amount, description identify the transaction (as in the ledger);
- question says what has to be checked;
- status is "open" or "closed" (the Italian "aperta"/"chiusa" are accepted too);
- resolution records what was found once closed.

Usage:
    uv run anomalies.py list [--all] [--month 2026-10]
    uv run anomalies.py add --date 2026-03-12 --amount -12.40 --question "What is this charge?" [--match esempio]
    uv run anomalies.py add --date 2026-03-31 --amount -120.00 --description "Bar Esempio (6 visits)" --question "..."
    uv run anomalies.py close --date 2026-03-12 --amount -12.40 --resolution "Streaming subscription"
"""

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from ledger import default_data_dir, find_transaction, read_transactions

ANOMALIES_FILE = "anomalies.csv"
COLUMNS = ["date", "amount", "description", "question", "status", "resolution"]
OPEN = "open"
CLOSED = "closed"
OPEN_VALUES = {"open", "aperta"}


@dataclass
class Anomaly:
    """One transaction to verify."""

    date: date
    amount: Decimal
    description: str
    question: str
    status: str = OPEN
    resolution: str = ""

    @property
    def is_open(self) -> bool:
        """True while the anomaly has not been resolved."""
        return self.status.strip().lower() in OPEN_VALUES


def load_anomalies(data_dir: Path) -> list[Anomaly]:
    """Read data/anomalies.csv; a missing file means no anomalies."""
    path = data_dir / ANOMALIES_FILE
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            Anomaly(
                date=date.fromisoformat(row["date"]),
                amount=Decimal(row["amount"]).quantize(Decimal("0.01")),
                description=row.get("description") or "",
                question=row.get("question") or "",
                status=row.get("status") or OPEN,
                resolution=row.get("resolution") or "",
            )
            for row in csv.DictReader(handle)
            if (row.get("date") or "").strip()
        ]


def save_anomalies(data_dir: Path, anomalies: list[Anomaly]) -> None:
    """Write data/anomalies.csv sorted by date."""
    path = data_dir / ANOMALIES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for anomaly in sorted(anomalies, key=lambda a: a.date):
            row = asdict(anomaly)
            row["date"] = anomaly.date.isoformat()
            row["amount"] = f"{anomaly.amount:.2f}"
            writer.writerow(row)


def main() -> int:
    """List, add and close anomalies."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    commands = parser.add_subparsers(dest="command")
    list_cmd = commands.add_parser("list", help="list open anomalies (default command)")
    list_cmd.add_argument("--all", action="store_true", help="include closed anomalies")
    list_cmd.add_argument("--month", help="restrict to a month, format YYYY-MM")
    add = commands.add_parser("add", help="add an anomaly for a ledger transaction (or a free one with --description)")
    close = commands.add_parser("close", help="close an open anomaly")
    for cmd in (add, close):
        cmd.add_argument("--date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
        cmd.add_argument("--amount", required=True, type=Decimal, help="signed, e.g. -12.40")
        cmd.add_argument("--match", default="", help="text of the description, when several transactions match")
    add.add_argument("--question", required=True, help="what has to be verified")
    add.add_argument("--description", help="free description (e.g. a monthly total): skips the ledger lookup")
    close.add_argument("--resolution", required=True, help="what was found")
    args = parser.parse_args()

    anomalies = load_anomalies(args.data_dir)
    if args.command == "add":
        description = args.description
        if not description:
            ledger = read_transactions(args.data_dir / "ledger.csv")
            description = find_transaction(ledger, args.date, args.amount, args.match).description
        anomalies.append(Anomaly(args.date, args.amount.quantize(Decimal("0.01")), description, args.question))
        save_anomalies(args.data_dir, anomalies)
        print(f"Added anomaly: {args.date} {args.amount} {description}")
        return 0
    if args.command == "close":
        targets = [
            a
            for a in anomalies
            if a.is_open
            and a.date == args.date
            and a.amount == args.amount
            and args.match.lower() in a.description.lower()
        ]
        if len(targets) != 1:
            print(f"Expected one open anomaly, found {len(targets)}; use --match", file=sys.stderr)
            return 1
        targets[0].status, targets[0].resolution = CLOSED, args.resolution
        save_anomalies(args.data_dir, anomalies)
        print(f"Closed anomaly: {targets[0].date} {targets[0].amount} {targets[0].description}")
        return 0

    show_all, month = getattr(args, "all", False), getattr(args, "month", None)
    selected = [a for a in anomalies if (show_all or a.is_open) and (not month or a.date.strftime("%Y-%m") == month)]
    for a in selected:
        print(f"[{a.status}] {a.date}  {a.amount:.2f}  {a.description}")
        print(f"    {a.question}")
        if a.resolution:
            print(f"    -> {a.resolution}")
    print(f"\n{len(selected)} anomalies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
