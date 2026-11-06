# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Map transactions to the user's own categories and subcategories.

The rules are private and live in data/categories.csv, with columns:

    bank_category,match,category,subcategory

A row applies to a transaction when:
- bank_category is empty or equal (case-insensitive) to the category given by the bank, and
- match is empty or matches the merchant or the raw description (substring, or /regex/ as in merchants.csv).

The first applying row wins, so specific rows (with "match") go before generic ones. A transaction that no row
covers keeps the bank category and is reported as unmapped, so the category list stays under the user's control.

Usage:
    uv run categories.py [--month 2026-10]   # show bank category -> user category, and what is still unmapped
"""

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from ledger import Transaction, cancel_reversals, default_data_dir, read_transactions
from merchants import MerchantRules, pattern_matches

CATEGORIES_FILE = "categories.csv"
UNCATEGORIZED = "Uncategorized"


@dataclass
class CategoryRule:
    """One row of categories.csv."""

    bank_category: str
    match: str
    category: str
    subcategory: str

    def applies(self, tx: Transaction, merchant: str) -> bool:
        """True when this rule covers the transaction."""
        if self.bank_category and self.bank_category.lower() != tx.category.lower():
            return False
        return not self.match or pattern_matches(self.match, merchant, tx.description)


@dataclass
class Categorized:
    """The user's classification of one transaction."""

    category: str
    subcategory: str
    mapped: bool


@dataclass
class CategoryRules:
    """The user's private category rules."""

    rules: list[CategoryRule]

    @classmethod
    def load(cls, data_dir: Path) -> "CategoryRules":
        """Load categories.csv from the data directory (missing file = bank categories as they are)."""
        path = data_dir / CATEGORIES_FILE
        if not path.exists():
            return cls([])
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return cls(
                [
                    CategoryRule(
                        (row.get("bank_category") or "").strip(),
                        (row.get("match") or "").strip(),
                        (row.get("category") or "").strip(),
                        (row.get("subcategory") or "").strip(),
                    )
                    for row in csv.DictReader(handle)
                    if (row.get("category") or "").strip()
                ]
            )

    def categorize(self, tx: Transaction, merchant: str) -> Categorized:
        """
        Classify a transaction.

        Args:
            tx: The transaction, with the bank category in tx.category
            merchant: The merchant name resolved by MerchantRules

        Returns:
            The user category and subcategory; mapped=False when no rule applied
        """
        for rule in self.rules:
            if rule.applies(tx, merchant):
                return Categorized(rule.category, rule.subcategory, True)
        return Categorized(tx.category or UNCATEGORIZED, "", not self.rules)


def main() -> int:
    """Show how the bank categories are mapped and which transactions no rule covers."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--month", help="restrict to a month, format YYYY-MM")
    args = parser.parse_args()

    merchants = MerchantRules.load(args.data_dir)
    categories = CategoryRules.load(args.data_dir)
    ledger, _ = cancel_reversals(read_transactions(args.data_dir / "ledger.csv"))
    expenses = [t for t in ledger if t.amount < 0 and (not args.month or t.date.strftime("%Y-%m") == args.month)]

    mapping: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    unmapped: list[tuple[Transaction, str]] = []
    for tx in expenses:
        merchant = merchants.merchant_for(tx.description)
        result = categories.categorize(tx, merchant)
        target = f"{result.category} / {result.subcategory}" if result.subcategory else result.category
        mapping[(result.category, target)][tx.category or UNCATEGORIZED] += tx.amount
        if not result.mapped:
            unmapped.append((tx, merchant))

    for (_, target), sources in sorted(mapping.items()):
        print(f"{target}  [{sum(sources.values()):.2f}]")
        for bank_category, total in sorted(sources.items()):
            print(f"    <- {bank_category}  [{total:.2f}]")
    if unmapped:
        print("\nUNMAPPED (add a row to categories.csv):")
        for tx, merchant in unmapped:
            print(f"    {tx.date}  {tx.category or UNCATEGORIZED}  |  {merchant}  |  {tx.amount:.2f}")
    print(f"\n{len(categories.rules)} rules, {len(expenses)} expenses, {len(unmapped)} unmapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
