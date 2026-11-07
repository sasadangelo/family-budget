# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Build the private HTML dashboards with every month in the ledger.

data/dashboard.html (year view, a year selector scopes the page):
1. yearly totals, then income, expenses and balance month by month;
2. income and expenses by category month by month (top categories, the rest folded into "Other");
3. recurring spending, one-off expenses, loans and the gap of recurring spending vs the ISTAT average.
Clicking a month opens its own dashboard.

data/dashboard/<YYYY-MM>.html (month view): the month's totals, income and expenses by category, recurring vs
one-off vs loans (with the one-off list) and the recurring spending vs ISTAT, group by group.

The page is self-contained (inline SVG and JavaScript, no external resources), so the data never leaves the computer.
It applies the same rules as the monthly report: user categories, reversals, one-offs, loans and ISTAT profile.

Usage:
    uv run dashboard.py [--language it] [--output data/dashboard.html]

The month pages are written next to the year page, in the dashboard/ folder.
"""

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from benchmark import BenchmarkProfile, Comparison, recurring_gap
from categories import CategoryRules
from i18n import TEXTS, Language, load_language
from ledger import Transaction, cancel_reversals, default_data_dir, read_transactions
from merchants import MerchantRules
from one_off import note_for, one_off_notes

TEMPLATE = Path(__file__).resolve().parent / "dashboard_template.html"
TOP_CATEGORIES = 7
MONTH_DIR = "dashboard"


@dataclass
class OneOffItem:
    """An extraordinary expense of the month, as listed by the month page."""

    date: str
    description: str
    note: str
    amount: Decimal


@dataclass
class MonthFigures:
    """The numbers of one month shown by the dashboard (expenses as positive amounts)."""

    month: str
    income: Decimal = Decimal(0)
    expenses: Decimal = Decimal(0)
    by_category: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    income_by_category: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    recurring_by_category: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    one_off: Decimal = Decimal(0)
    loans: Decimal = Decimal(0)
    benchmark: Decimal | None = None
    one_off_items: list[OneOffItem] = field(default_factory=list)
    comparisons: list[Comparison] = field(default_factory=list)

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
        if tx.amount > 0:  # income keeps the bank categories, as in the monthly report
            figures.income += tx.amount
            figures.income_by_category[tx.category] += tx.amount
            continue
        spent = -tx.amount
        result = categories.categorize(tx, merchants.merchant_for(tx.description))
        figures.expenses += spent
        figures.by_category[result.category] += spent
        note = note_for(tx, one_offs)
        if note:
            figures.one_off += spent
            figures.one_off_items.append(OneOffItem(tx.date.isoformat(), tx.description, note, spent))
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
        figures.comparisons = benchmark.compare(ordinary)
    return figures


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(round(value, 2))


def _fold(
    months: list[MonthFigures],
    amounts: Callable[[MonthFigures], dict[str, Decimal]],
    rank: Callable[[str], tuple[Decimal, ...]],
    top: int,
) -> tuple[list[str], list[str], list[str]]:
    """Categories that get a colour, categories folded into "Other", every category by total (largest first)."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for m in months:
        for category, amount in amounts(m).items():
            totals[category] += amount
    ranked = sorted(totals, key=rank)
    shown = ranked[:top] if len(ranked) > top + 1 else ranked
    return shown, [c for c in ranked if c not in shown], sorted(totals, key=lambda c: -totals[c])


def _series(amounts: dict[str, Decimal], shown: list[str], folded: list[str], other: str) -> dict[str, float | None]:
    """A month's amounts on the coloured categories, the folded ones summed into "Other"."""
    result = {c: _money(amounts.get(c, Decimal(0))) for c in shown}
    if folded:
        result[other] = _money(sum((amounts.get(c, Decimal(0)) for c in folded), Decimal(0)))
    return result


def _labels(language: Language) -> dict[str, str]:
    return {k: v for k, v in TEXTS[language.code].items() if k.startswith("dash_") or k == "months"}


def _summary(m: MonthFigures) -> dict[str, float | None | str]:
    return {
        "month": m.month,
        "income": _money(m.income),
        "expenses": _money(m.expenses),
        "balance": _money(m.balance),
        "recurring": _money(m.recurring),
        "one_off": _money(m.one_off),
        "loans": _money(m.loans),
        "benchmark": _money(m.benchmark),
        "gap": _money(m.gap),
    }


def dashboard_data(months: list[MonthFigures], language: Language, top: int = TOP_CATEGORIES) -> dict[str, object]:
    """The JSON payload embedded in the year page."""
    labels = _labels(language)
    other = labels["dash_other"]
    recurring: dict[str, Decimal] = defaultdict(Decimal)
    spent: dict[str, Decimal] = defaultdict(Decimal)
    received: dict[str, Decimal] = defaultdict(Decimal)
    for m in months:
        for category, amount in m.by_category.items():
            spent[category] += amount
            recurring[category] += m.recurring_by_category.get(category, Decimal(0))
        for category, amount in m.income_by_category.items():
            received[category] += amount
    # expense colours go to the highest recurring spending: one-offs and loans must not hide them
    shown, folded, every = _fold(months, lambda m: m.by_category, lambda c: (-recurring[c], -spent[c]), top)
    in_shown, in_folded, in_every = _fold(months, lambda m: m.income_by_category, lambda c: (-received[c],), top)
    return {
        "page": "year",
        "language": language.code,
        "labels": labels,
        "month_dir": MONTH_DIR,
        "categories": shown + ([other] if folded else []),
        "folded": folded,
        "all_categories": every,
        "income_categories": in_shown + ([other] if in_folded else []),
        "income_folded": in_folded,
        "all_income_categories": in_every,
        "months": [
            {
                **_summary(m),
                "all_by_category": {c: _money(m.by_category.get(c, Decimal(0))) for c in every},
                "by_category": _series(m.by_category, shown, folded, other),
                "all_income_by_category": {c: _money(m.income_by_category.get(c, Decimal(0))) for c in in_every},
                "income_by_category": _series(m.income_by_category, in_shown, in_folded, other),
            }
            for m in months
        ],
    }


def month_data(
    months: list[MonthFigures], index: int, language: Language, year: dict[str, object]
) -> dict[str, object]:
    """
    The JSON payload embedded in the page of months[index].

    Args:
        months: Every month of the ledger; the neighbours give the previous/next links
        index: Position of the month in months
        language: Page language
        year: The year page payload, whose coloured categories the month page reuses (same colour on both pages)
    """
    m = months[index]

    def ranked(amounts: dict[str, Decimal]) -> list[dict[str, object]]:
        return [{"name": c, "amount": _money(v)} for c, v in sorted(amounts.items(), key=lambda kv: -kv[1]) if v]

    return {
        "page": "month",
        "language": language.code,
        "labels": _labels(language),
        "categories": year["categories"],
        "income_categories": year["income_categories"],
        "month": {
            **_summary(m),
            "expenses_by_category": ranked(m.by_category),
            "income_by_category": ranked(m.income_by_category),
            "one_off_items": [
                {"date": o.date, "description": o.description, "note": o.note, "amount": _money(o.amount)}
                for o in sorted(m.one_off_items, key=lambda o: o.date)
            ],
            "comparisons": [
                {"label": c.label, "spent": _money(c.spent), "benchmark": _money(c.benchmark)}
                for c in sorted(m.comparisons, key=lambda c: -c.difference)
            ],
        },
        "previous": months[index - 1].month if index > 0 else None,
        "next": months[index + 1].month if index + 1 < len(months) else None,
    }


def render(data: dict[str, object]) -> str:
    """Fill the HTML template with the data (escaped so that it cannot close the script tag)."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__LANG__", str(data["language"])).replace("/*__DATA__*/{}", payload)


def build_dashboards(data_dir: Path, language: Language) -> tuple[str, dict[str, str]]:
    """Compute every month of the ledger; return the year page and the month pages keyed by YYYY-MM."""
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
    year = dashboard_data(months, language)
    pages = {m.month: render(month_data(months, i, language, year)) for i, m in enumerate(months)}
    return render(year), pages


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
    year_page, month_pages = build_dashboards(args.data_dir, load_language(args.data_dir, args.language))
    output.write_text(year_page, encoding="utf-8")
    month_dir = output.parent / MONTH_DIR
    month_dir.mkdir(exist_ok=True)
    for month, page in month_pages.items():
        (month_dir / f"{month}.html").write_text(page, encoding="utf-8")
    print(f"Saved {output} and {len(month_pages)} month pages in {month_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
