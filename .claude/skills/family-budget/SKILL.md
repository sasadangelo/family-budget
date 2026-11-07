---
name: family-budget
description: Personal and household expense tracking. Imports bank statements and transaction lists from any bank (PDF, CSV, Excel, also several files per month), merges them into a single ledger without duplicates, recognises merchants and categories, tracks anomalies and one-off expenses, compares spending with the ISTAT (Italian statistics) averages and every month generates three reports (main, statistics, details) in the user's language. Use when the user asks to import bank reports, produce a month's report, analyse where the money goes, flag or close anomalies, mark extraordinary expenses or compare with the average household.
---

# Family budget

Pipeline: **bank files → ledger → merchants and categories → anomalies and one-offs → reports**.
The code is generic: no bank-specific rules. Everything personal lives in the private data folder `data/` (entirely
excluded from git), never in the code.

Talk to the user in their language. Reports are written in the language set in `data/settings.json`.

## Folders and files

| Path | Content |
|---|---|
| `data/settings.json` | user settings, e.g. `{"language": "it"}` (report language: `en` default, `it`) |
| `data/reports/` | original bank files, dropped there by the user |
| `data/ledger.csv` | all transactions in the canonical format (never edit by hand) |
| `data/merchants.csv` | merchant aliases (`pattern,merchant`) |
| `data/merchant_stopwords.txt` | words stripped from the end of merchant names (cities), one per line |
| `data/categories.csv` | the user's categories (`bank_category,match,category,subcategory`) |
| `data/anomalies.csv` | transactions to verify (`date,amount,description,question,status,resolution`) |
| `data/one_off.csv` | extraordinary one-off expenses (`date,amount,description,note`) |
| `data/benchmark.json` | ISTAT comparison profile (household type, threshold, category mapping) |
| `data/YYYY-MM/income-expenses.md` | main monthly report |
| `data/YYYY-MM/income-expenses-stats.md` | rankings: merchants and biggest expenses |
| `data/YYYY-MM/income-expenses-details.md` | every transaction, category by category |
| `data/dashboard.html` | private dashboard with every month (open it in a browser) |
| `data/dashboard/YYYY-MM.html` | private dashboard of one month (opened by clicking the month) |

The data folder can be moved with the environment variable `FAMILY_BUDGET_DATA`.
References: [references/conventions.md](references/conventions.md) (canonical format, input levels, merchants,
reversals), [references/istat-benchmarks.md](references/istat-benchmarks.md) (ISTAT averages and comparison method),
`references/istat-2025.json` (the same figures, read by the code).

Scripts live in this skill's `scripts/` and run from the project root with `uv run <skill>/scripts/<name>.py`
(`<skill>` = `.claude/skills/family-budget`; `uv` installs the dependencies declared in the script). Always use these
commands to change files in `data/`: do not write ad-hoc code and never try out commands that write on real data.

## First setup

If `data/settings.json` does not exist, ask the user which language they want for the reports and create it.
Categories, merchant rules and the ISTAT profile are built up during the first months (steps 2-4).

## Monthly procedure

When the user asks for a month's report (e.g. "do the November report"), follow the steps in order.

### 1. Import

```bash
uv run <skill>/scripts/extract_transactions.py --dry-run   # check
uv run <skill>/scripts/extract_transactions.py             # save into the ledger
```

For each file it prints number of transactions, period, totals and the **detected layout**. Re-importing is safe:
duplicates are skipped. Before saving:
- if the document states the number of transactions or totals, compare them with the output;
- check that the layout makes sense (the description must not be the category column);
- if every date has day ≤ 12 the script assumes day/month: confirm by looking at the file.

If a file fails (`[FAIL]`: scan, photo, free text), read it yourself and write a CSV in the canonical format in
`data/reports/<name>.csv`, then import again. Never change the code to fit one bank.
Transactions not yet booked by the bank are imported anyway: what matters is that the money left.

### 2. Merchants

```bash
uv run <skill>/scripts/merchants.py --month YYYY-MM
```

Shows each merchant with the raw descriptions grouped under it. For variants of the same merchant add a row to
`data/merchants.csv` (`pattern` = text searched case-insensitively, or `/regex/`; `merchant` = name to use; first
match wins); for cities or countries at the end of names add the word to `data/merchant_stopwords.txt`. If a merge is
not obvious, ask the user first.

### 3. Categories

```bash
uv run <skill>/scripts/categories.py --month YYYY-MM
```

Bank categories are mapped to the user's categories by `data/categories.csv`: bank category (empty = any), optional
`match` on merchant or description (same syntax as aliases), user category and subcategory. The first applying row
wins, so rows with `match` go first. For every **unmapped** transaction ask the user where it belongs, unless obvious.

### 4. One-offs and anomalies

Point out to the user the transactions that look exceptional (unusually large) or suspicious (unknown charges,
duplicates, odd frequencies) and ask how to treat them. Record the answers with the commands:

```bash
# extraordinary expenses: the note uses the user's own words
uv run <skill>/scripts/one_off.py add --date YYYY-MM-DD --amount -250.00 --note "New washing machine"
uv run <skill>/scripts/one_off.py remove --date YYYY-MM-DD --amount -250.00
uv run <skill>/scripts/one_off.py list --month YYYY-MM

# anomalies: a ledger transaction, or a free summary with --description
uv run <skill>/scripts/anomalies.py add --date YYYY-MM-DD --amount -12.40 --question "What is this charge?"
uv run <skill>/scripts/anomalies.py add --date YYYY-MM-DD --amount -120.00 --description "Bar Esempio (6 visits)" --question "..."
uv run <skill>/scripts/anomalies.py close --date YYYY-MM-DD --amount -12.40 --resolution "Checked: regular expense"
uv run <skill>/scripts/anomalies.py list --month YYYY-MM
```

If several transactions share date and amount, add `--match <text of the description>`.

### 5. Reports

```bash
uv run <skill>/scripts/monthly_report.py --month YYYY-MM [--language it]
```

Writes three files in `data/YYYY-MM/`, always with the same sections in the same order.

`income-expenses.md`:
1. summary: income, expenses, balance, transactions, savings rate; note "Expenses = recurring + one-off + loans";
2. anomalies to verify (only if open ones exist for the month);
3. expenses by category (with subcategories; ⚠️ on bank categories not yet mapped);
4. income by category (bank categories);
5. recurring spending vs the ISTAT average (only if `data/benchmark.json` exists);
6. extraordinary (one-off) expenses, with notes and total;
7. excluded reversals (only if any).

`income-expenses-stats.md`: merchants where most is spent, most visited merchants, biggest expenses
(`--top-merchants`, `--top-expenses`, default 10).

`income-expenses-details.md`: every transaction of each expense and income category, with bank description, bank
category, subcategory and total.

### 6. Dashboard

```bash
uv run <skill>/scripts/dashboard.py
```

Regenerates `data/dashboard.html` (year view) and one page per month in `data/dashboard/YYYY-MM.html`.

Year view: a year selector scopes the page. On top the yearly totals (income, expenses, balance) and the latest
month with data; then four half-width widgets on the 12 months of the year (months without data stay empty):
income/expenses/balance; income and expenses by category, with an Expenses/Income switch (the 7 categories with the
highest recurring spending, or income, get a colour, the rest is folded into "Other", the table lists all);
recurring vs one-off vs loans (yearly totals on top); recurring spending vs the ISTAT average (latest month on top,
gap month by month below). Clicking a month in any chart opens its month page.

Month view: the month's income, expenses, balance and savings rate; income and expenses by category (level bar with
the same colours as the year view, then one bar per category); recurring vs one-off vs loans with the list of the
month's one-off expenses; recurring spending vs ISTAT group by group. Links go back to the year and to the
previous/next month.

The pages are self-contained (no external resources) and stay in `data/`: never publish them as an artifact or
anywhere else.

After the reports, summarise the key points for the user (balance, expense split, categories over the average, open
anomalies) without repeating every table.

## Calculation rules

- **Reversals**: a reversal (storno/rimborso/refund… in category or description) that finds the payment it cancels
  (same amount, opposite sign, within the previous 60 days) is excluded from the report **together with the
  payment**. A reversal without a payment stays as income. The ledger is never modified.
- **One-offs**: they stay in their categories (totals match the bank) and are listed in their own section; they are
  excluded only from recurring spending and from the ISTAT comparison.
- **Loans**: the categories in `excluded_categories` of `data/benchmark.json` (e.g. mortgage and loans) are excluded
  from recurring spending, because ISTAT does not count them as consumption.
- **ISTAT comparison**: recurring spending is compared with the user's household type, removing from the average the
  items in `excluded_istat` (e.g. imputed rent for home owners). Each ISTAT item is scaled by household-type spending /
  Italian average. The table lists the categories over the threshold (in euro, largest first), the others above
  average, the offset from categories below average, the items not compared, and the **recurring over budget** total,
  which is their sum. Profile format: docstring of `scripts/benchmark.py`. To set it up ask for the household type and
  map the categories to the ISTAT items; cash, loans and mixed items stay out. The benchmark covers Italian households;
  for other countries it can be left unconfigured.
- When ISTAT publishes a new year (usually in October), update `references/istat-2025.json` (or add the new year's file
  and update `ISTAT_FILE` in `scripts/benchmark.py`) and `references/istat-benchmarks.md`.

## Adding a report language

Add the language to `TEXTS` and `FORMATS` in `scripts/i18n.py` (every key of `en` must be present).

## Verification

`uv run pytest` also runs `tests/test_end_to_end.py`: an invented month processed with every command, in Italian and
in English, checking the three reports and the order of their sections. Run it after every change to the scripts.
