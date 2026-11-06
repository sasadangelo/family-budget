# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Derive the merchant (shop, payee, counterpart) of a transaction from its description.

Two layers:
1. A generic clean-up that removes what banks typically add around the merchant name: transaction-type prefixes,
   payment-processor prefixes, mandate ids, reference codes, street addresses. No bank-specific rules.
2. Private, user-specific rules kept in the data directory (never in the code):
   - merchant_stopwords.txt: words removed from the end of a name, one per line (typically the cities where the
     user shops), so "Bakery Springfield" and "Bakery" become the same merchant.
   - merchants.csv (columns "pattern,merchant"): maps the cleaned name or the raw description to the name the user
     wants. A pattern is a case-insensitive substring, or a regular expression when written between slashes
     (/.../). The first matching row wins.

Usage:
    uv run merchants.py [--month 2026-10]   # list merchants with their raw variants, to curate the alias file
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from ledger import Transaction, default_data_dir, normalize_text, read_transactions

ALIASES_FILE = "merchants.csv"
STOPWORDS_FILE = "merchant_stopwords.txt"

_PREFIXES = re.compile(
    r"^(addebito diretto disposto a favore di|bonifico disposto a favore di|bonifico disposto da|"
    r"bonifico a favore di|bonifico da|pagamento pos|pagamento|payment to|payment from|card payment to|"
    r"direct debit to|transfer to|transfer from)\b\s*:?\s*",
    re.IGNORECASE,
)
_PROCESSORS = re.compile(r"^(paypal|sumup|sq|zettle|nexi|satispay|stripe)\s*\*\s*", re.IGNORECASE)
_MANDATE = re.compile(r"\b(mandato|mandate|rif\.?|ref\.?|cro|trn)\b\s*:?\s*\S+", re.IGNORECASE)
_ADDRESS = re.compile(
    r"\s(via|viale|v\.le|piazza|p\.za|p\.zza|corso|c\.so|largo|lungomare|strada|street|road|avenue)\b.*$",
    re.IGNORECASE,
)
_TRUNCATED_ADDRESS = re.compile(r"\s(vi|v\.?)$", re.IGNORECASE)
_CODE_TOKEN = re.compile(r"\b\S*\d\S*\b")


def pattern_matches(pattern: str, *texts: str) -> bool:
    """
    Match a user pattern: case-insensitive substring, or a regular expression when written as /.../.

    Args:
        pattern: The pattern written by the user
        texts: Texts to test; the pattern matches if it matches any of them
    """
    if len(pattern) > 2 and pattern.startswith("/") and pattern.endswith("/"):
        regex = re.compile(pattern[1:-1], re.IGNORECASE)
        return any(regex.search(t) for t in texts)
    needle = pattern.lower()
    return any(needle in t.lower() for t in texts)


@dataclass
class AliasRule:
    """One row of the alias file."""

    pattern: str
    merchant: str

    def matches(self, *texts: str) -> bool:
        """True when the pattern matches any of the given texts."""
        return pattern_matches(self.pattern, *texts)


def clean_description(description: str, stopwords: set[str] | None = None) -> str:
    """
    Generic clean-up of a bank description into a merchant-like name.

    Examples:
        "Addebito diretto disposto a favore di: Energia Esempio SPA MANDATO: AB12" -> "Energia Esempio SPA"
        "Pizzeria Esempio Via Lunga 12" -> "Pizzeria Esempio"
        "Shop* X1y2z3 Online" -> "Shop"

    Args:
        description: Raw bank description
        stopwords: Lower-case words to strip from the end of the name (e.g. cities)
    """
    text = normalize_text(description)
    text = _PREFIXES.sub("", text)
    text = _PROCESSORS.sub("", text)
    text = _MANDATE.sub("", text)
    if "*" in text:
        text = text.split("*", 1)[0]
    text = _ADDRESS.sub("", " " + text).strip()
    text = _TRUNCATED_ADDRESS.sub("", text)
    text = _CODE_TOKEN.sub("", text)
    text = re.sub(r"[\s\-.,:;/]+$", "", re.sub(r"\s+", " ", text)).strip()
    words = text.split()
    while len(words) > 1 and words[-1].lower().strip(".,") in (stopwords or set()):
        words.pop()
    text = " ".join(words)
    if not text:
        return normalize_text(description)
    return text.title() if text.isupper() or text.islower() else text


@dataclass
class MerchantRules:
    """The user's private rules to turn descriptions into merchant names."""

    aliases: list[AliasRule]
    stopwords: set[str]

    @classmethod
    def load(cls, data_dir: Path) -> "MerchantRules":
        """Load merchants.csv and merchant_stopwords.txt from the data directory (both optional)."""
        aliases: list[AliasRule] = []
        alias_path = data_dir / ALIASES_FILE
        if alias_path.exists():
            with alias_path.open(newline="", encoding="utf-8-sig") as handle:
                aliases = [
                    AliasRule(row["pattern"].strip(), row["merchant"].strip())
                    for row in csv.DictReader(handle)
                    if (row.get("pattern") or "").strip() and (row.get("merchant") or "").strip()
                ]
        stopwords: set[str] = set()
        stopwords_path = data_dir / STOPWORDS_FILE
        if stopwords_path.exists():
            lines = stopwords_path.read_text(encoding="utf-8").splitlines()
            stopwords = {w.strip().lower() for w in lines if w.strip() and not w.startswith("#")}
        return cls(aliases, stopwords)

    def merchant_for(self, description: str) -> str:
        """Return the merchant of a transaction description."""
        cleaned = clean_description(description, self.stopwords)
        for rule in self.aliases:
            if rule.matches(cleaned, description):
                return rule.merchant
        return cleaned


def main() -> int:
    """List merchants and the raw descriptions grouped under each one."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", type=Path, default=default_data_dir() / "ledger.csv")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="where the rule files live")
    parser.add_argument("--month", help="restrict to a month, format YYYY-MM")
    args = parser.parse_args()

    rules = MerchantRules.load(args.data_dir)
    transactions: list[Transaction] = [
        t for t in read_transactions(args.ledger) if not args.month or t.date.strftime("%Y-%m") == args.month
    ]
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        groups[rules.merchant_for(tx.description)].append(tx)

    for merchant, items in sorted(groups.items(), key=lambda kv: kv[0].lower()):
        total = sum((t.amount for t in items), Decimal(0))
        print(f"{merchant}  [{len(items)} tx, {total:.2f}]")
        for raw in sorted({t.description for t in items}):
            print(f"    {raw}")
    print(f"\n{len(groups)} merchants, {len(transactions)} transactions")
    print(f"{len(rules.aliases)} alias rules, {len(rules.stopwords)} stopwords")
    return 0


if __name__ == "__main__":
    sys.exit(main())
