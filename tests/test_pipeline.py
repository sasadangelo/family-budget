# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
Tests for extraction, ledger merge and merchant clean-up. All data here is invented.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import openpyxl
import pytest
from anomalies import Anomaly, load_anomalies, save_anomalies
from benchmark import BenchmarkProfile, recurring_gap
from categories import Categorized, CategoryRules
from extract_transactions import LayoutError, extract_file, tables_to_transactions
from ledger import (
    Transaction,
    cancel_reversals,
    merge_into_ledger,
    parse_amount,
    parse_date,
    read_transactions,
    write_transactions,
)
from merchants import MerchantRules, clean_description
from one_off import OneOff, note_for, one_off_notes, save_one_offs

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("€ -1.234,56", "-1234.56"),
        ("-1,234.56", "-1234.56"),
        ("1234.5", "1234.50"),
        ("1.234", "1234.00"),
        ("-37,80 EUR", "-37.80"),
        ("+12", "12.00"),
    ],
)
def test_parse_amount(text: str, expected: str) -> None:
    assert parse_amount(text) == Decimal(expected)


def test_parse_date_formats() -> None:
    assert parse_date("31.10.2026") == date(2026, 10, 31)
    assert parse_date("2026-10-31") == date(2026, 10, 31)
    assert parse_date("10/31/26", day_first=False) == date(2026, 10, 31)


def test_signed_amount_table_split_across_pages() -> None:
    page1 = [
        ["Lista movimenti", "", ""],
        ["Data", "Descrizione", "Importo"],
        ["31.10.2026", "Supermercato\nEsempio", "€ -10,00"],
    ]
    page2 = [["Data", "Descrizione", "Importo"], ["13.10.2026", "Stipendio", "€ 1.500,00"]]
    transactions, _ = tables_to_transactions([page1, page2], "x.pdf")
    assert [(t.date.day, t.description, t.amount) for t in transactions] == [
        (31, "Supermercato Esempio", Decimal("-10.00")),
        (13, "Stipendio", Decimal("1500.00")),
    ]


def test_debit_credit_columns_with_balance() -> None:
    transactions, _ = extract_file(FIXTURES / "dare_avere.csv", account="conto", currency="EUR")
    assert [t.amount for t in transactions] == [Decimal("-25.40"), Decimal("1200.00"), Decimal("-3.10")]
    assert transactions[0].description == "Panificio Esempio"
    assert transactions[0].category == "Alimentari"
    assert {t.account for t in transactions} == {"conto"}


def test_month_first_dates_are_detected() -> None:
    table = [["Date", "Details", "Amount"], ["10/31/2026", "Coffee", "-3.50"], ["10/02/2026", "Salary", "2000"]]
    transactions, _ = tables_to_transactions([table], "x.csv")
    assert [t.date for t in transactions] == [date(2026, 10, 31), date(2026, 10, 2)]


def test_xlsx(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Data operazione", "Causale", "Importo"])
    sheet.append([date(2026, 10, 5), "Libreria Esempio", -12.9])
    path = tmp_path / "movimenti.xlsx"
    workbook.save(path)
    transactions, _ = extract_file(path, "", "EUR")
    assert transactions[0].date == date(2026, 10, 5)
    assert transactions[0].amount == Decimal("-12.90")


def test_ambiguous_layout_is_an_error() -> None:
    table = [["Data", "Descrizione", "A", "B"], ["01.10.2026", "Negozio", "10,00", "5,00"]]
    with pytest.raises(LayoutError):
        tables_to_transactions([table], "x.csv")


def test_canonical_csv_roundtrip(tmp_path: Path) -> None:
    tx = Transaction(date(2026, 10, 1), "Negozio", Decimal("-1.50"), category="Varie", source_file="a.pdf")
    path = tmp_path / "ledger.csv"
    write_transactions(path, [tx])
    transactions, how = extract_file(path, "", "EUR")
    assert how == "canonical CSV"
    assert transactions == read_transactions(path) == [tx]


def test_merge_keeps_legitimate_repeats_and_skips_overlaps() -> None:
    topup = Transaction(date(2026, 3, 7), "Ricarica Esempio", Decimal("-7.50"))
    other = Transaction(date(2026, 3, 8), "Bar", Decimal("-1.20"))
    ledger, added = merge_into_ledger([], [topup, topup])
    assert added == 2
    ledger, added = merge_into_ledger(ledger, [topup, topup, other])
    assert added == 1 and len(ledger) == 3


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Addebito diretto disposto a favore di: Esempio Energia SPA MANDATO: 12AB34", "Esempio Energia SPA"),
        ("Bonifico disposto da: MARIO ROSSI", "Mario Rossi"),
        ("Pizzeria Esempio Via Lunga 12", "Pizzeria Esempio"),
        ("Shop* X1y2z3 Online", "Shop"),
        ("SumUp *PALESTRA ESEMPIO", "Palestra Esempio"),
        ("Ferramenta Esempio Srl Vi", "Ferramenta Esempio Srl"),
        ("Negozio Esempio 1234 Paperopoli", "Negozio Esempio Paperopoli"),
    ],
)
def test_clean_description(raw: str, expected: str) -> None:
    assert clean_description(raw) == expected


def test_private_rules(tmp_path: Path) -> None:
    (tmp_path / "merchant_stopwords.txt").write_text("# cities\nPaperopoli\n")
    (tmp_path / "merchants.csv").write_text("pattern,merchant\nSuper Esempio,Super Esempio\n/^bar ?x/,Bar X\n")
    rules = MerchantRules.load(tmp_path)
    assert rules.merchant_for("Negozio Esempio Paperopoli") == "Negozio Esempio"
    assert rules.merchant_for("Super Esempio-filiale Via Lunga") == "Super Esempio"
    assert rules.merchant_for("BARX Paperopoli") == "Bar X"


def test_reversal_cancels_only_its_payment() -> None:
    payment = Transaction(date(2026, 3, 5), "Pagamento Pos", Decimal("-80.00"), category="Varie")
    reversal = Transaction(date(2026, 3, 9), "Storno Pagamento Pos", Decimal("80.00"), category="Rimborsi")
    transfer_out = Transaction(date(2026, 3, 3), "Bonifico a Mario", Decimal("-15.00"))
    transfer_in = Transaction(date(2026, 3, 3), "Bonifico da Mario", Decimal("15.00"))
    orphan = Transaction(date(2026, 3, 10), "Rimborso spese", Decimal("40.00"))
    kept, pairs = cancel_reversals([payment, transfer_out, transfer_in, reversal, orphan])
    assert pairs == [(payment, reversal)]
    assert kept == [transfer_out, transfer_in, orphan]


def test_category_rules(tmp_path: Path) -> None:
    (tmp_path / "categories.csv").write_text(
        "bank_category,match,category,subcategory\n"
        ",Energia Esempio,Utenze,Luce\n"
        "Cellulare,,Utenze,Telefono\n"
        "Farmacia,,Salute,\n"
    )
    rules = CategoryRules.load(tmp_path)
    bill = Transaction(date(2026, 10, 1), "Addebito Energia Esempio", Decimal("-50"), category="Domiciliazioni")
    phone = Transaction(date(2026, 10, 1), "Ricarica", Decimal("-10"), category="cellulare")
    other = Transaction(date(2026, 10, 1), "Pizzeria", Decimal("-20"), category="Ristoranti")
    assert rules.categorize(bill, "Energia Esempio") == Categorized("Utenze", "Luce", True)
    assert rules.categorize(phone, "Ricarica") == Categorized("Utenze", "Telefono", True)
    assert rules.categorize(other, "Pizzeria") == Categorized("Ristoranti", "", False)
    assert CategoryRules([]).categorize(other, "Pizzeria").mapped


def test_anomalies_roundtrip(tmp_path: Path) -> None:
    anomaly = Anomaly(date(2026, 3, 12), Decimal("-12.40"), "Addebito Esempio", "Cos'è?")
    save_anomalies(tmp_path, [anomaly])
    assert load_anomalies(tmp_path) == [anomaly]
    assert anomaly.is_open and not Anomaly(date(2026, 1, 1), Decimal(0), "x", "y", status="Chiusa").is_open


def test_one_off_notes_match_transactions(tmp_path: Path) -> None:
    tx = Transaction(date(2026, 3, 16), "Elettrodomestici  Esempio", Decimal("-250.00"))
    save_one_offs(tmp_path, [OneOff(tx.date, tx.amount, "elettrodomestici esempio", "Lavatrice")])
    notes = one_off_notes(tmp_path)
    assert note_for(tx, notes) == "Lavatrice"
    assert note_for(Transaction(date(2026, 3, 16), "Altro", Decimal("-250.00")), notes) is None


def test_benchmark_threshold(tmp_path: Path) -> None:
    (tmp_path / "benchmark.json").write_text(
        '{"household": "Coppia con 2 figli", "threshold_percent": 20, "groups": ['
        '{"label": "Vestiti", "categories": ["Abbigliamento"], "istat": ["Abbigliamento e calzature"]},'
        '{"label": "Cibo", "categories": ["Spesa"], "istat": ["Prodotti alimentari e bevande analcoliche"]}]}'
    )
    profile = BenchmarkProfile.load(tmp_path)
    assert profile is not None and round(profile.scale, 2) == Decimal("1.30")
    over = profile.over_threshold({"Abbigliamento": Decimal("300"), "Spesa": Decimal("700")})
    assert [c.label for c in over] == ["Vestiti"]
    assert BenchmarkProfile.load(tmp_path / "missing") is None


def test_recurring_gap_adds_up(tmp_path: Path) -> None:
    (tmp_path / "benchmark.json").write_text(
        '{"household": "Coppia con 2 figli", "threshold_percent": 10,'
        ' "excluded_categories": ["Rate"], "excluded_istat": ["Affitti figurativi"], "groups": ['
        '{"label": "Vestiti", "categories": ["Abbigliamento"], "istat": ["Abbigliamento e calzature"]},'
        '{"label": "Cibo", "categories": ["Spesa"], "istat": ["Prodotti alimentari e bevande analcoliche"]}]}'
    )
    profile = BenchmarkProfile.load(tmp_path)
    assert profile is not None
    spent = {"Abbigliamento": Decimal("300"), "Spesa": Decimal("500"), "Rate": Decimal("700")}
    gap = recurring_gap(profile, spent, Decimal("3500"))
    assert gap.spent == Decimal("2800") and gap.benchmark == Decimal("3618.44") - Decimal("611.44")
    assert [c.label for c in gap.over_threshold] == ["Vestiti"] and [c.label for c in gap.under] == ["Cibo"]
    parts = sum((c.difference for c in gap.over_threshold + gap.under), Decimal(0)) + gap.not_comparable
    assert parts == gap.total
