# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Report language: labels, month names and number formatting.

The language is read from the private file data/settings.json, e.g. {"language": "it"}; default is English.
To add a language, add an entry to TEXTS (every key of "en" must be present) and to FORMATS.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

SETTINGS_FILE = "settings.json"
DEFAULT_LANGUAGE = "en"

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "months": "January,February,March,April,May,June,July,August,September,October,November,December",
        "title": "Income and expenses: {period}",
        "title_stats": "Income and expenses: statistics, {period}",
        "title_details": "Income and expenses: details, {period}",
        "uncategorized": "Uncategorized",
        "item": "Item",
        "amount": "Amount",
        "income": "Income",
        "expenses": "Expenses",
        "balance": "Balance",
        "transactions": "Transactions",
        "transactions_value": "{total} ({income} income, {expenses} expenses)",
        "savings_rate": "Savings rate",
        "expenses_split": "Expenses = recurring spending {recurring} + one-off {one_off}",
        "expenses_split_loans": " + loan installments {loans}",
        "anomalies": "⚠️ Anomalies to verify ({count})",
        "date": "Date",
        "transaction": "Transaction",
        "to_verify": "To verify",
        "expenses_by_category": "Expenses by category",
        "income_by_category": "Income by category",
        "category": "Category",
        "total": "Total",
        "share_of_expenses": "% of expenses",
        "count": "Transactions",
        "unmapped": "⚠️ Bank categories not yet assigned to one of your categories: {names}.",
        "benchmark": "Recurring spending vs the ISTAT average (one-off expenses excluded)",
        "spent": "Spent",
        "benchmark_value": "Estimated ISTAT average",
        "difference": "Difference",
        "difference_pct": "Difference %",
        "over_below_threshold": "Other above average, within {threshold}% ({items})",
        "compensation": "Offset: below average ({items})",
        "not_comparable": "Items not compared one by one (cash, utilities, other expenses)",
        "over_budget": "Recurring over budget",
        "benchmark_note": "In bold the categories more than {threshold}% above average. Reference: {household}, "
        "ISTAT {year}; ISTAT items scaled by ×{scale}; excluded from the total: {excluded}.",
        "one_off": "Extraordinary (one-off) expenses: {total}",
        "merchant": "Merchant",
        "note": "Note",
        "reversals": "Excluded reversals (payment and reversal cancel each other)",
        "payment": "Payment",
        "reversal": "Reversal",
        "description": "Description",
        "sources": "Sources: {sources}. Distinct merchants: {merchants}.",
        "top_spending": "Merchants: where you spend the most (top {top})",
        "top_visits": "Merchants: where you go most often (top {top})",
        "visits": "Visits",
        "average": "Average",
        "biggest": "The {top} biggest expenses",
        "detail_heading": "{category}: {total} ({count} transactions)",
        "bank_description": "Bank description",
        "bank_category": "Bank category",
        "subcategory": "Subcategory",
        "from": "From",
        "dash_title": "Family budget",
        "dash_year": "Year {year}: income and expenses",
        "dash_year_income": "Income in the year",
        "dash_year_expenses": "Expenses in the year",
        "dash_year_balance": "Balance of the year",
        "dash_latest_month": "Latest month with data",
        "dash_click_hint": "Click a month in any chart to open its dashboard.",
        "dash_open_month": "Open the dashboard of {month}",
        "dash_month_subtitle": "Income, expenses and recurring spending of the month",
        "dash_month_income": "Income of the month",
        "dash_month_expenses": "Expenses of the month",
        "dash_month_balance": "Balance of the month",
        "dash_savings_rate": "Savings rate",
        "dash_back": "Year {year}",
        "dash_share": "Share",
        "dash_one_off_list": "One-off expenses of the month",
        "dash_no_one_off": "No one-off expenses this month.",
        "dash_date": "Date",
        "dash_description": "Description",
        "dash_note": "Note",
        "dash_amount": "Amount",
        "dash_groups": "Gap by group",
        "dash_group": "Group",
        "dash_spent": "Spent",
        "dash_not_compared": "Not compared one by one",
        "dash_no_data": "No data this month.",
        "dash_year_label": "Year",
        "dash_split": "Recurring, one-off and loans",
        "dash_subtitle": "Income, expenses and recurring spending, month by month in the selected year",
        "dash_month": "Month",
        "dash_category": "Category",
        "dash_income": "Income",
        "dash_expenses": "Expenses",
        "dash_balance": "Balance",
        "dash_cashflow": "Income, expenses and balance",
        "dash_categories": "Income and expenses by category",
        "dash_widget": "Recurring spending vs ISTAT average",
        "dash_recurring": "Recurring",
        "dash_one_off": "One-off",
        "dash_loans": "Loans",
        "dash_benchmark": "ISTAT average",
        "dash_gap": "Gap vs ISTAT",
        "dash_gap_chart": "Recurring spending gap vs ISTAT, month by month",
        "dash_over": "over budget",
        "dash_under": "under budget",
        "dash_no_benchmark": "ISTAT comparison not configured (data/benchmark.json).",
        "dash_other": "Other",
        "dash_table": "Show the table",
        "dash_total": "Total",
        "dash_folded": "Other includes: {names}.",
    },
    "it": {
        "months": "Gennaio,Febbraio,Marzo,Aprile,Maggio,Giugno,Luglio,Agosto,Settembre,Ottobre,Novembre,Dicembre",
        "title": "Entrate e uscite: {period}",
        "title_stats": "Entrate e uscite: statistiche, {period}",
        "title_details": "Entrate e uscite: dettaglio, {period}",
        "uncategorized": "Non categorizzato",
        "item": "Voce",
        "amount": "Importo",
        "income": "Entrate",
        "expenses": "Uscite",
        "balance": "Saldo",
        "transactions": "Movimenti",
        "transactions_value": "{total} ({income} entrate, {expenses} uscite)",
        "savings_rate": "Risparmio sulle entrate",
        "expenses_split": "Uscite = spesa ricorrente {recurring} + una tantum {one_off}",
        "expenses_split_loans": " + rate {loans}",
        "anomalies": "⚠️ Anomalie da verificare ({count})",
        "date": "Data",
        "transaction": "Movimento",
        "to_verify": "Da verificare",
        "expenses_by_category": "Uscite per categoria",
        "income_by_category": "Entrate per categoria",
        "category": "Categoria",
        "total": "Totale",
        "share_of_expenses": "% uscite",
        "count": "Movimenti",
        "unmapped": "⚠️ Categorie della banca non ancora assegnate a una tua categoria: {names}.",
        "benchmark": "Spesa ricorrente rispetto alla media ISTAT (senza spese una tantum)",
        "spent": "Speso",
        "benchmark_value": "Media ISTAT stimata",
        "difference": "Differenza",
        "difference_pct": "Differenza %",
        "over_below_threshold": "Altre sopra la media, entro il {threshold}% ({items})",
        "compensation": "Compensazione: sotto la media ({items})",
        "not_comparable": "Voci non confrontabili una per una (contanti, utenze, altre uscite)",
        "over_budget": "Fuori budget ricorrente",
        "benchmark_note": "In grassetto le categorie oltre il {threshold}% della media. Riferimento: {household}, "
        "ISTAT {year}; voci ISTAT scalate di ×{scale}; esclusi dal totale: {excluded}.",
        "one_off": "Spese straordinarie (una tantum): {total}",
        "merchant": "Negozio",
        "note": "Nota",
        "reversals": "Storni esclusi (pagamento e storno si annullano)",
        "payment": "Pagamento",
        "reversal": "Storno",
        "description": "Descrizione",
        "sources": "Fonti: {sources}. Negozi distinti: {merchants}.",
        "top_spending": "Negozi: dove spendi di più (top {top})",
        "top_visits": "Negozi: dove vai più spesso (top {top})",
        "visits": "Visite",
        "average": "Media",
        "biggest": "Le {top} spese più grandi",
        "detail_heading": "{category}: {total} ({count} movimenti)",
        "bank_description": "Descrizione banca",
        "bank_category": "Categoria banca",
        "subcategory": "Sottocategoria",
        "from": "Da",
        "dash_title": "Bilancio familiare",
        "dash_year": "Anno {year}: entrate e uscite",
        "dash_year_income": "Entrate dell'anno",
        "dash_year_expenses": "Uscite dell'anno",
        "dash_year_balance": "Saldo dell'anno",
        "dash_latest_month": "Ultimo mese con dati",
        "dash_click_hint": "Clicca su un mese in un grafico per aprirne la dashboard.",
        "dash_open_month": "Apri la dashboard di {month}",
        "dash_month_subtitle": "Entrate, uscite e spesa ricorrente del mese",
        "dash_month_income": "Entrate del mese",
        "dash_month_expenses": "Uscite del mese",
        "dash_month_balance": "Saldo del mese",
        "dash_savings_rate": "Tasso di risparmio",
        "dash_back": "Anno {year}",
        "dash_share": "Quota",
        "dash_one_off_list": "Spese una tantum del mese",
        "dash_no_one_off": "Nessuna spesa una tantum nel mese.",
        "dash_date": "Data",
        "dash_description": "Descrizione",
        "dash_note": "Nota",
        "dash_amount": "Importo",
        "dash_groups": "Scarto per gruppo",
        "dash_group": "Gruppo",
        "dash_spent": "Speso",
        "dash_not_compared": "Non confrontate una per una",
        "dash_no_data": "Nessun dato nel mese.",
        "dash_year_label": "Anno",
        "dash_split": "Ricorrente, una tantum e rate",
        "dash_subtitle": "Entrate, uscite e spesa ricorrente, mese per mese nell'anno scelto",
        "dash_month": "Mese",
        "dash_category": "Categoria",
        "dash_income": "Entrate",
        "dash_expenses": "Uscite",
        "dash_balance": "Saldo",
        "dash_cashflow": "Entrate, uscite e saldo",
        "dash_categories": "Entrate e uscite per categoria",
        "dash_widget": "Spesa ricorrente rispetto alla media ISTAT",
        "dash_recurring": "Ricorrente",
        "dash_one_off": "Una tantum",
        "dash_loans": "Rate",
        "dash_benchmark": "Media ISTAT",
        "dash_gap": "Scarto vs ISTAT",
        "dash_gap_chart": "Scarto della spesa ricorrente rispetto a ISTAT, mese per mese",
        "dash_over": "fuori budget",
        "dash_under": "sotto budget",
        "dash_no_benchmark": "Confronto ISTAT non configurato (data/benchmark.json).",
        "dash_other": "Altre",
        "dash_table": "Mostra la tabella",
        "dash_total": "Totale",
        "dash_folded": "Altre comprende: {names}.",
    },
}

# thousands separator, decimal separator, currency before the number
FORMATS: dict[str, tuple[str, str, bool]] = {"en": (",", ".", True), "it": (".", ",", False)}


@dataclass
class Language:
    """Labels and number formatting for one report language."""

    code: str

    def __post_init__(self) -> None:
        if self.code not in TEXTS:
            raise ValueError(f"Unsupported language {self.code!r}; available: {', '.join(sorted(TEXTS))}")

    def t(self, key: str, **values: object) -> str:
        """Translate a label, filling the {placeholders}."""
        return TEXTS[self.code][key].format(**values)

    def month(self, yyyy_mm: str) -> str:
        """Human month, e.g. "October 2026"."""
        year, month = yyyy_mm.split("-")
        return f"{self.t('months').split(',')[int(month) - 1]} {year}"

    def number(self, value: Decimal, decimals: int = 2) -> str:
        """Format a number with the language separators."""
        thousands, decimal, _ = FORMATS[self.code]
        text = f"{abs(value):,.{decimals}f}".replace(",", "\0").replace(".", decimal).replace("\0", thousands)
        return f"{'-' if value < 0 else ''}{text}"

    def money(self, value: Decimal) -> str:
        """Format an amount in euro: "1.234,56 €" (it), "€1,234.56" (en)."""
        _, _, before = FORMATS[self.code]
        number = self.number(abs(value))
        text = f"€{number}" if before else f"{number} €"
        return f"-{text}" if value < 0 else text

    def percent(self, value: Decimal) -> str:
        """Format a percentage with one decimal."""
        return f"{self.number(value, 1)}%"


def load_language(data_dir: Path, override: str | None = None) -> Language:
    """Read the report language from data/settings.json (or use the override)."""
    if override:
        return Language(override)
    path = data_dir / SETTINGS_FILE
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return Language(settings.get("language", DEFAULT_LANGUAGE))
