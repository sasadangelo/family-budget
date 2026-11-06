# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Build the monthly income/expense reports (Markdown) from the ledger, in <data>/<YYYY-MM>/:
income-expenses.md (main report), income-expenses-stats.md (rankings), income-expenses-details.md (all movements
by category).

Usage:
    uv run monthly_report.py --month 2026-10 [--top-merchants 10] [--top-expenses 10]
"""

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from anomalies import Anomaly, load_anomalies
from benchmark import BenchmarkProfile, Comparison, recurring_gap
from categories import CategoryRules
from i18n import Language, load_language
from ledger import Transaction, cancel_reversals, default_data_dir, read_transactions
from merchants import MerchantRules
from one_off import note_for, one_off_notes


@dataclass
class Bucket:
    """Aggregate of the transactions sharing a category or a merchant."""

    total: Decimal = Decimal(0)
    count: int = 0
    categories: Counter[str] = field(default_factory=Counter)

    def add(self, tx: Transaction) -> None:
        """Account one transaction."""
        self.total += tx.amount
        self.count += 1
        self.categories[tx.category] += 1


def _group(transactions: list[Transaction], key: Callable[[Transaction], str]) -> dict[str, Bucket]:
    buckets: dict[str, Bucket] = defaultdict(Bucket)
    for tx in transactions:
        buckets[key(tx)].add(tx)
    return buckets


def _table(headers: list[str], rows: list[list[str]], right: set[int]) -> list[str]:
    align = ["---:" if i in right else "---" for i in range(len(headers))]
    lines = [f"| {' | '.join(headers)} |", f"| {' | '.join(align)} |"]
    lines += [f"| {' | '.join(cell.replace('|', '\\|') for cell in r)} |" for r in rows]
    return lines + [""]


@dataclass
class MonthlyReport:
    """The three Markdown files produced for a month."""

    main: str
    stats: str
    details: str

    def save(self, directory: Path) -> list[Path]:
        """Write income-expenses.md, income-expenses-stats.md and income-expenses-details.md into directory."""
        directory.mkdir(parents=True, exist_ok=True)
        files = {
            "income-expenses.md": self.main,
            "income-expenses-stats.md": self.stats,
            "income-expenses-details.md": self.details,
        }
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")
        return [directory / name for name in files]


def build_report(
    transactions: list[Transaction],
    month: str,
    rules: MerchantRules,
    categories: CategoryRules,
    top_merchants: int,
    top_expenses: int,
    cancelled: list[tuple[Transaction, Transaction]] | None = None,
    anomalies: list[Anomaly] | None = None,
    one_offs: dict[tuple[str, str, str], str] | None = None,
    benchmark: BenchmarkProfile | None = None,
    language: Language | None = None,
) -> MonthlyReport:
    """
    Render the Markdown reports of one month: main report, statistics and per-category details.

    Args:
        transactions: Transactions of the month
        month: Month in YYYY-MM format
        rules: Private merchant rules
        categories: Private category rules (expenses only; income keeps the bank categories)
        top_merchants: How many merchants to list in each merchant ranking (by spending, by visits)
        top_expenses: How many of the biggest expenses to list
        cancelled: (payment, reversal) pairs excluded because they cancel each other
        anomalies: Open anomalies of the month, listed at the top of the report
        one_offs: Extraordinary expenses (transaction key -> note), shown apart from ordinary spending
        benchmark: ISTAT comparison profile; categories over the threshold are listed (one-offs excluded)
        language: Report language (default English)

    Returns:
        The three reports as Markdown
    """
    lang = language or Language("en")
    t_, money, pct = lang.t, lang.money, lang.percent
    uncategorized = t_("uncategorized")
    transactions = [replace(t, category=t.category or uncategorized) for t in transactions]
    period = lang.month(month)
    income = [t for t in transactions if t.amount > 0]
    classified = [
        (t, categories.categorize(t, rules.merchant_for(t.description))) for t in transactions if t.amount < 0
    ]
    expenses = [replace(t, category=c.category) for t, c in classified]
    subcategories = [c.subcategory for _, c in classified]
    unmapped = _group([t for t, c in classified if not c.mapped], lambda t: t.category)
    total_in = sum((t.amount for t in income), Decimal(0))
    total_out = sum((t.amount for t in expenses), Decimal(0))
    net = total_in + total_out
    out_abs = -total_out
    notes = {id(t): n for t, _ in classified if (n := note_for(t, one_offs or {}))}
    extraordinary = [(t, c, notes[id(t)]) for t, c in classified if id(t) in notes]
    total_extra = sum((t.amount for t, _, _ in extraordinary), Decimal(0))

    def signed(value: Decimal) -> str:
        return f"+{money(value)}" if value > 0 else money(value)

    def day(value: date) -> str:
        return value.strftime("%d/%m")

    lines = [f"# {t_('title', period=period)}", ""]
    lines += _table(
        [t_("item"), t_("amount")],
        [
            [t_("income"), money(total_in)],
            [t_("expenses"), money(total_out)],
            [f"**{t_('balance')}**", f"**{money(net)}**"],
            [
                t_("transactions"),
                t_("transactions_value", total=len(transactions), income=len(income), expenses=len(expenses)),
            ],
            [t_("savings_rate"), pct(net / total_in * 100) if total_in else "-"],
        ],
        {1},
    )
    loan_categories = benchmark.excluded_categories if benchmark else []
    loans = sum((-t.amount for t, c in classified if id(t) not in notes and c.category in loan_categories), Decimal(0))
    if extraordinary or loans:
        split = t_("expenses_split", recurring=money(out_abs + total_extra - loans), one_off=money(-total_extra))
        if loans:
            split += t_("expenses_split_loans", loans=money(loans))
        lines += [f"_{split}._", ""]

    if anomalies:
        lines += [f"## {t_('anomalies', count=len(anomalies))}", ""]
        lines += _table(
            [t_("date"), t_("transaction"), t_("amount"), t_("to_verify")],
            [[day(a.date), a.description, money(a.amount), a.question] for a in anomalies],
            {2},
        )

    lines += [f"## {t_('expenses_by_category')}", ""]
    by_category = sorted(_group(expenses, lambda t: t.category).items(), key=lambda kv: kv[1].total)
    category_rows: list[list[str]] = []
    for category, bucket in by_category:
        subs: dict[str, Bucket] = defaultdict(Bucket)
        for tx, sub in zip(expenses, subcategories):
            if tx.category == category and sub:
                subs[sub].add(tx)
        name = f"**{category}**" if subs else category
        if category in unmapped:
            name += " ⚠️"
        category_rows.append([name, money(bucket.total), pct(-bucket.total / out_abs * 100), str(bucket.count)])
        for sub, sub_bucket in sorted(subs.items(), key=lambda kv: kv[1].total):
            category_rows.append(
                [f"&nbsp;&nbsp;↳ {sub}", money(sub_bucket.total), pct(-sub_bucket.total / out_abs * 100),
                 str(sub_bucket.count)]
            )  # fmt: skip
    lines += _table([t_("category"), t_("total"), t_("share_of_expenses"), t_("count")], category_rows, {1, 2, 3})
    if unmapped:
        lines += [t_("unmapped", names=", ".join(sorted(unmapped))), ""]

    lines += [f"## {t_('income_by_category')}", ""]
    by_source = sorted(_group(income, lambda t: t.category).items(), key=lambda kv: -kv[1].total)
    lines += _table(
        [t_("category"), t_("total"), t_("count")],
        [[c, money(b.total), str(b.count)] for c, b in by_source],
        {1, 2},
    )

    if benchmark:
        ordinary: dict[str, Decimal] = defaultdict(Decimal)
        for t, c in classified:
            if id(t) not in notes:
                ordinary[c.category] -= t.amount
                if c.subcategory:
                    ordinary[f"{c.category} / {c.subcategory}"] -= t.amount
        total_ordinary = sum((-t.amount for t, _ in classified if id(t) not in notes), Decimal(0))
        gap = recurring_gap(benchmark, ordinary, total_ordinary)
        threshold = f"{benchmark.threshold_percent:.0f}"
        lines += [f"## {t_('benchmark')}", ""]

        def labels(items: list[Comparison]) -> str:
            return ", ".join(f"{c.label} {signed(c.difference)}" for c in items)

        rows = [
            [f"**{c.label}**", money(c.spent), money(c.benchmark), f"**{signed(c.difference)}**", f"+{pct(c.percent)}"]
            for c in gap.over_threshold
        ]
        if gap.over_below_threshold:
            total = sum((c.difference for c in gap.over_below_threshold), Decimal(0))
            label = t_("over_below_threshold", threshold=threshold, items=labels(gap.over_below_threshold))
            rows.append([label, "", "", signed(total), ""])
        if gap.under:
            total = sum((c.difference for c in gap.under), Decimal(0))
            rows.append([t_("compensation", items=labels(gap.under)), "", "", signed(total), ""])
        rows.append([t_("not_comparable"), "", "", signed(gap.not_comparable), ""])
        gap_percent = gap.total / gap.benchmark * 100
        gap_percent_text = f"{'+' if gap_percent > 0 else ''}{pct(gap_percent)}"
        rows.append([f"**{t_('over_budget')}**", f"**{money(gap.spent)}**", f"**{money(gap.benchmark)}**",
                     f"**{signed(gap.total)}**", f"**{gap_percent_text}**"])  # fmt: skip
        headers = [t_("category"), t_("spent"), t_("benchmark_value"), t_("difference"), t_("difference_pct")]
        lines += _table(headers, rows, {1, 2, 3, 4})
        note = t_(
            "benchmark_note",
            threshold=threshold,
            household=benchmark.household,
            year=benchmark.istat["year"],
            scale=lang.number(benchmark.scale),
            excluded=", ".join(benchmark.excluded_categories + benchmark.excluded_istat),
        )
        lines += [f"_{note}_", ""]

    if extraordinary:
        lines += [f"## {t_('one_off', total=money(total_extra))}", ""]
        rows = [
            [day(t.date), rules.merchant_for(t.description), c.category, note, money(t.amount)]
            for t, c, note in sorted(extraordinary, key=lambda it: it[0].date)
        ]
        rows.append(["", "", "", f"**{t_('total')}**", f"**{money(total_extra)}**"])
        lines += _table([t_("date"), t_("merchant"), t_("category"), t_("note"), t_("amount")], rows, {4})

    if cancelled:
        lines += [f"## {t_('reversals')}", ""]
        lines += _table(
            [t_("payment"), t_("reversal"), t_("description"), t_("amount")],
            [[day(p.date), day(r.date), p.description, money(p.amount)] for p, r in cancelled],
            {3},
        )

    stats = [f"# {t_('title_stats', period=period)}", ""]
    merchants = _group(expenses, lambda t: rules.merchant_for(t.description))

    def merchant_row(name: str, bucket: Bucket) -> list[str]:
        category = bucket.categories.most_common(1)[0][0]
        return [name, category, str(bucket.count), money(bucket.total), money(bucket.total / bucket.count)]

    headers = [t_("merchant"), t_("category"), t_("visits"), t_("total"), t_("average")]
    stats += [f"## {t_('top_spending', top=top_merchants)}", ""]
    by_spend = sorted(merchants.items(), key=lambda kv: kv[1].total)[:top_merchants]
    stats += _table(headers, [merchant_row(n, b) for n, b in by_spend], {2, 3, 4})

    stats += [f"## {t_('top_visits', top=top_merchants)}", ""]
    frequent = sorted(
        ((n, b) for n, b in merchants.items() if b.count > 1), key=lambda kv: (-kv[1].count, kv[1].total)
    )[:top_merchants]
    stats += _table(headers, [merchant_row(n, b) for n, b in frequent], {2, 3, 4})

    stats += [f"## {t_('biggest', top=top_expenses)}", ""]
    biggest = sorted(expenses, key=lambda t: t.amount)[:top_expenses]
    stats += _table(
        [t_("date"), t_("merchant"), t_("category"), t_("amount")],
        [[day(t.date), rules.merchant_for(t.description), t.category, money(t.amount)] for t in biggest],
        {3},
    )

    details = [f"# {t_('title_details', period=period)}", ""]
    details += [f"## {t_('expenses_by_category')}", ""]
    for category, bucket in by_category:
        items = [(t, c) for t, c in classified if c.category == category]
        has_subs = any(c.subcategory for _, c in items)
        sub_totals: dict[str, Decimal] = defaultdict(Decimal)
        for t, c in items:
            sub_totals[c.subcategory] += t.amount
        items.sort(key=lambda it: (sub_totals[it[1].subcategory], it[1].subcategory, it[0].date))
        details += [f"### {t_('detail_heading', category=category, total=money(bucket.total), count=bucket.count)}", ""]
        headers = [t_("date"), t_("merchant"), t_("bank_description"), t_("bank_category")]
        headers += [t_("subcategory")] if has_subs else []
        rows = [
            [day(t.date), rules.merchant_for(t.description), t.description, t.category]
            + ([c.subcategory] if has_subs else [])
            + [money(t.amount)]
            for t, c in items
        ]
        rows.append(["", "", "", f"**{t_('total')}**"] + ([""] if has_subs else []) + [f"**{money(bucket.total)}**"])
        details += _table(headers + [t_("amount")], rows, {len(headers)})

    details += [f"## {t_('income_by_category')}", ""]
    for category, bucket in by_source:
        received = sorted((t for t in income if t.category == category), key=lambda t: t.date)
        details += [f"### {t_('detail_heading', category=category, total=money(bucket.total), count=bucket.count)}", ""]
        rows = [[day(t.date), rules.merchant_for(t.description), t.description, money(t.amount)] for t in received]
        rows.append(["", "", f"**{t_('total')}**", f"**{money(bucket.total)}**"])
        details += _table([t_("date"), t_("from"), t_("bank_description"), t_("amount")], rows, {3})

    sources = ", ".join(sorted({t.source_file for t in transactions}))
    lines += [f"_{t_('sources', sources=sources, merchants=len(merchants))}_", ""]
    return MonthlyReport("\n".join(lines), "\n".join(stats), "\n".join(details))


def main() -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", required=True, help="month to report, format YYYY-MM")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--top-merchants", type=int, default=10)
    parser.add_argument("--top-expenses", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, help="default: <data-dir>/<month>/")
    parser.add_argument("--language", help="report language (default: data/settings.json, else en)")
    args = parser.parse_args()

    ledger, pairs = cancel_reversals(read_transactions(args.data_dir / "ledger.csv"))
    transactions = [t for t in ledger if t.date.strftime("%Y-%m") == args.month]
    cancelled = [(p, r) for p, r in pairs if args.month in (p.date.strftime("%Y-%m"), r.date.strftime("%Y-%m"))]
    if not transactions:
        print(f"No transactions for {args.month} in {args.data_dir / 'ledger.csv'}", file=sys.stderr)
        return 1
    merchants, categories = MerchantRules.load(args.data_dir), CategoryRules.load(args.data_dir)
    anomalies = [a for a in load_anomalies(args.data_dir) if a.is_open and a.date.strftime("%Y-%m") == args.month]
    report = build_report(
        transactions,
        args.month,
        merchants,
        categories,
        args.top_merchants,
        args.top_expenses,
        cancelled,
        anomalies,
        one_off_notes(args.data_dir),
        BenchmarkProfile.load(args.data_dir),
        load_language(args.data_dir, args.language),
    )
    for path in report.save(args.output_dir or args.data_dir / args.month):
        print(f"Saved {path}", file=sys.stderr)
    print(report.main)
    return 0


if __name__ == "__main__":
    sys.exit(main())
