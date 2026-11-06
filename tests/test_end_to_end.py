# *******************************************************************************
# © Copyright sasadangelo 2026
# ******************************************************************************/
"""
End-to-end test: a whole month processed with the skill's commands, on invented data in a temporary directory.
It guarantees that every month produces the same three reports with the same sections in the same order.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "family-budget" / "scripts"

BANK_EXPORT = """Lista movimenti Banca Esempio
Data;Descrizione;Categoria;Importo
03/11/2026;Supermercato Esempio Paperopoli;Alimentari;-85,40
05/11/2026;Supermercato Esempio Via Lunga;Alimentari;-60,10
06/11/2026;Addebito diretto disposto a favore di: Energia Esempio SPA MANDATO: AB12;Utenze;-90,00
08/11/2026;Pagamento Pos;Varie;-50,00
10/11/2026;Storno Pagamento Pos;Rimborsi;50,00
12/11/2026;Negozio Vestiti Esempio;Abbigliamento;-400,00
15/11/2026;Mobilificio Esempio;Casa;-900,00
20/11/2026;Rata Mutuo;Mutuo;-700,00
27/11/2026;Stipendio;Stipendi;3000,00
"""

EN_SECTIONS = (
    [
        "# Income and expenses: November 2026",
        "## ⚠️ Anomalies to verify (1)",
        "## Expenses by category",
        "## Income by category",
        "## Recurring spending vs the ISTAT average (one-off expenses excluded)",
        "## Extraordinary (one-off) expenses: -€900.00",
        "## Excluded reversals (payment and reversal cancel each other)",
    ],
    [
        "# Income and expenses: statistics, November 2026",
        "## Merchants: where you spend the most (top 10)",
        "## Merchants: where you go most often (top 10)",
        "## The 10 biggest expenses",
    ],
    ["# Income and expenses: details, November 2026", "## Expenses by category", "## Income by category"],
)
MAIN_SECTIONS = [
    "# Entrate e uscite: Novembre 2026",
    "## ⚠️ Anomalie da verificare (1)",
    "## Uscite per categoria",
    "## Entrate per categoria",
    "## Spesa ricorrente rispetto alla media ISTAT (senza spese una tantum)",
    "## Spese straordinarie (una tantum): -900,00 €",
    "## Storni esclusi (pagamento e storno si annullano)",
]
STATS_SECTIONS = [
    "# Entrate e uscite: statistiche, Novembre 2026",
    "## Negozi: dove spendi di più (top 10)",
    "## Negozi: dove vai più spesso (top 10)",
    "## Le 10 spese più grandi",
]
DETAILS_SECTIONS = [
    "# Entrate e uscite: dettaglio, Novembre 2026",
    "## Uscite per categoria",
    "## Entrate per categoria",
]


def run(data_dir: Path, script: str, *args: str) -> str:
    """Run one of the skill's scripts against the given data directory."""
    env = {**os.environ, "FAMILY_BUDGET_DATA": str(data_dir)}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args], env=env, cwd=data_dir, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout + result.stderr


def headings(path: Path) -> list[str]:
    """Level 1 and 2 headings of a Markdown file, in order."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if re.match(r"^#{1,2} ", line)]


@pytest.mark.parametrize("language", ["it", "en"])
def test_month_produces_the_three_reports(tmp_path: Path, language: str) -> None:
    data = tmp_path / "data"
    (data / "reports").mkdir(parents=True)
    (data / "settings.json").write_text(json.dumps({"language": language}))
    (data / "reports" / "novembre.csv").write_text(BANK_EXPORT, encoding="utf-8")
    (data / "merchant_stopwords.txt").write_text("Paperopoli\n", encoding="utf-8")
    (data / "merchants.csv").write_text("pattern,merchant\nSupermercato Esempio,Supermercato Esempio\n")
    (data / "categories.csv").write_text(
        "bank_category,match,category,subcategory\n"
        ",Energia Esempio,Utenze,Luce\n"
        "Alimentari,,Spesa,\n"
        "Abbigliamento,,Vestiti,\n"
        "Casa,,Casa,\n"
        "Mutuo,,Rate,\n"
        "Varie,,Altro,\n"
    )
    (data / "benchmark.json").write_text(
        json.dumps(
            {
                "household": "Coppia con 2 figli",
                "threshold_percent": 10,
                "excluded_categories": ["Rate"],
                "excluded_istat": ["Affitti figurativi"],
                "groups": [
                    {"label": "Vestiti", "categories": ["Vestiti"], "istat": ["Abbigliamento e calzature"]},
                    {"label": "Spesa", "categories": ["Spesa"], "istat": ["Prodotti alimentari e bevande analcoliche"]},
                ],
            }
        )
    )

    out = run(data, "extract_transactions.py")
    assert "[OK] novembre.csv: 9 transactions" in out
    assert "added to ledger: 0" in run(data, "extract_transactions.py"), "re-import must not duplicate"
    assert "0 unmapped" in run(data, "categories.py", "--month", "2026-11")
    assert "Supermercato Esempio  [2 tx" in run(data, "merchants.py", "--month", "2026-11")

    run(data, "one_off.py", "add", "--date", "2026-11-15", "--amount", "-900.00", "--note", "Nuovo armadio")
    run(data, "anomalies.py", "add", "--date", "2026-11-12", "--amount", "-400.00", "--question", "Cosa?")
    run(data, "anomalies.py", "add", "--date", "2026-11-03", "--amount", "-85.40", "--question", "Chi?")
    run(data, "anomalies.py", "close", "--date", "2026-11-03", "--amount", "-85.40", "--resolution", "Ok")

    run(data, "monthly_report.py", "--month", "2026-11")
    month = data / "2026-11"
    run(data, "dashboard.py")
    page = (data / "dashboard.html").read_text(encoding="utf-8")
    payload = json.loads(re.search(r'id="data">(.*?)</script>', page, re.S).group(1))
    november = payload["months"][0]
    assert november["month"] == "2026-11" and november["recurring"] == 635.5 and november["one_off"] == 900.0
    assert november["loans"] == 700.0 and november["gap"] is not None
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=", page), "the dashboard must not load external resources"
    if language == "en":
        main_sections, stats_sections, details_sections = EN_SECTIONS
        assert headings(month / "income-expenses.md") == main_sections
        assert headings(month / "income-expenses-stats.md") == stats_sections
        assert headings(month / "income-expenses-details.md") == details_sections
        assert "| Expenses | -€2,235.50 |" in (month / "income-expenses.md").read_text(encoding="utf-8")
        return
    assert headings(month / "income-expenses.md") == MAIN_SECTIONS
    assert headings(month / "income-expenses-stats.md") == STATS_SECTIONS
    assert headings(month / "income-expenses-details.md") == DETAILS_SECTIONS

    main = (month / "income-expenses.md").read_text(encoding="utf-8")
    assert "| Uscite | -2.235,50 € |" in main, "the cancelled POS payment and its reversal are excluded"
    assert "_Uscite = spesa ricorrente 635,50 € + una tantum 900,00 € + rate 700,00 €._" in main
    assert "| **Vestiti** |" in main and "**Fuori budget ricorrente**" in main
    assert "| &nbsp;&nbsp;↳ Luce | -90,00 € |" in main
    details = (month / "income-expenses-details.md").read_text(encoding="utf-8")
    assert "### Spesa: -145,50 € (2 movimenti)" in details
