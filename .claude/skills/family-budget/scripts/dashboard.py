# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Build the private HTML dashboard (data/dashboard.html) with every month in the ledger:

1. income, expenses and balance month by month;
2. expenses by category month by month (top categories, the rest folded into "Other");
3. recurring spending, one-off expenses, loans and the gap of recurring spending vs the ISTAT average.

The page is self-contained (inline SVG and JavaScript, no external resources), so the data never leaves the computer.
It applies the same rules as the monthly report: user categories, reversals, one-offs, loans and ISTAT profile.

Usage:
    uv run dashboard.py [--language it] [--output data/dashboard.html]
"""

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from benchmark import BenchmarkProfile, recurring_gap
from categories import CategoryRules
from i18n import TEXTS, Language, load_language
from ledger import Transaction, cancel_reversals, default_data_dir, read_transactions
from merchants import MerchantRules
from one_off import note_for, one_off_notes

TEMPLATE = Path(__file__).resolve().parent / "dashboard_template.html"
TOP_CATEGORIES = 7


@dataclass
class MonthFigures:
    """The numbers of one month shown by the dashboard (expenses as positive amounts)."""

    month: str
    income: Decimal = Decimal(0)
    expenses: Decimal = Decimal(0)
    by_category: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    recurring_by_category: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    one_off: Decimal = Decimal(0)
    loans: Decimal = Decimal(0)
    benchmark: Decimal | None = None

    @property
    def balance(self) -> Decimal:
        """Income minus expenses."""
        return self.income - self.expenses

    @property
    def recurring(self) -> Decimal:
        """Expenses without one-offs and loan installments."""
        return self.expenses - self.one_off - self.loans

    @property
    def gap(self) -> Decimal | None:
        """Recurring spending minus the ISTAT benchmark (positive = over budget)."""
        return None if self.benchmark is None else self.recurring - self.benchmark


def month_figures(
    transactions: list[Transaction],
    month: str,
    merchants: MerchantRules,
    categories: CategoryRules,
    one_offs: dict[tuple[str, str, str], str],
    benchmark: BenchmarkProfile | None,
    uncategorized: str,
) -> MonthFigures:
    """Compute the dashboard figures of one month from its transactions (reversals already cancelled)."""
    figures = MonthFigures(month)
    ordinary: dict[str, Decimal] = defaultdict(Decimal)
    for tx in transactions:
        tx = replace(tx, category=tx.category or uncategorized)
        if tx.amount > 0:
            figures.income += tx.amount
            continue
        spent = -tx.amount
        result = categories.categorize(tx, merchants.merchant_for(tx.description))
        figures.expenses += spent
        figures.by_category[result.category] += spent
        if note_for(tx, one_offs):
            figures.one_off += spent
            continue
        if benchmark and result.category in benchmark.excluded_categories:
            figures.loans += spent
        else:
            figures.recurring_by_category[result.category] += spent
        ordinary[result.category] += spent
        if result.subcategory:
            ordinary[f"{result.category} / {result.subcategory}"] += spent
    if benchmark:
        total_ordinary = figures.expenses - figures.one_off
        figures.benchmark = recurring_gap(benchmark, ordinary, total_ordinary).benchmark
    return figures


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 2))


def dashboard_data(months: list[MonthFigures], language: Language, top: int = TOP_CATEGORIES) -> dict[str, object]:
    """The JSON payload embedded in the page."""
    recurring: dict[str, Decimal] = defaultdict(Decimal)
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for m in months:
        for category, amount in m.by_category.items():
            totals[category] += amount
            recurring[category] += m.recurring_by_category.get(category, Decimal(0))
    # colours go to the categories with the highest recurring spending: one-offs and loans must not hide them
    ranked = sorted(totals, key=lambda c: (-recurring[c], -totals[c]))
    shown = ranked[:top] if len(ranked) > top + 1 else ranked
    folded = [c for c in ranked if c not in shown]
    labels = {k: v for k, v in TEXTS[language.code].items() if k.startswith("dash_") or k == "months"}
    return {
        "language": language.code,
        "labels": labels,
        "categories": shown + ([labels["dash_other"]] if folded else []),
        "folded": folded,
        "all_categories": sorted(totals, key=lambda c: -totals[c]),
        "months": [
            {
                "month": m.month,
                "income": _money(m.income),
                "expenses": _money(m.expenses),
                "balance": _money(m.balance),
                "recurring": _money(m.recurring),
                "one_off": _money(m.one_off),
                "loans": _money(m.loans),
                "benchmark": _money(m.benchmark),
                "gap": _money(m.gap),
                "all_by_category": {c: _money(m.by_category.get(c, Decimal(0))) for c in totals},
                "by_category": {
                    **{c: _money(m.by_category.get(c, Decimal(0))) for c in shown},
                    **(
                        {
                            labels["dash_other"]: _money(
                                sum((m.by_category.get(c, Decimal(0)) for c in folded), Decimal(0))
                            )
                        }
                        if folded
                        else {}
                    ),
                },
            }
            for m in months
        ],
    }


def render(data: dict[str, object]) -> str:
    """Fill the HTML template with the data (escaped so that it cannot close the script tag)."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__LANG__", str(data["language"])).replace("/*__DATA__*/{}", payload)


def build_dashboard(data_dir: Path, language: Language) -> str:
    """Compute every month of the ledger and render the dashboard page."""
    ledger, _ = cancel_reversals(read_transactions(data_dir / "ledger.csv"))
    merchants, categories = MerchantRules.load(data_dir), CategoryRules.load(data_dir)
    one_offs, benchmark = one_off_notes(data_dir), BenchmarkProfile.load(data_dir)
    by_month: dict[str, list[Transaction]] = defaultdict(list)
    for tx in ledger:
        by_month[tx.date.strftime("%Y-%m")].append(tx)
    uncategorized = language.t("uncategorized")
    months = [
        month_figures(by_month[m], m, merchants, categories, one_offs, benchmark, uncategorized)
        for m in sorted(by_month)
    ]
    return render(dashboard_data(months, language))


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--language", help="dashboard language (default: data/settings.json, else en)")
    parser.add_argument("--output", type=Path, help="default: <data-dir>/dashboard.html")
    args = parser.parse_args()

    if not (args.data_dir / "ledger.csv").exists():
        print(f"No ledger in {args.data_dir}", file=sys.stderr)
        return 1
    output = args.output or args.data_dir / "dashboard.html"
    output.write_text(build_dashboard(args.data_dir, load_language(args.data_dir, args.language)), encoding="utf-8")
    print(f"Saved {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
