# family-budget

A [Claude Code](https://claude.com/claude-code) skill to track household income and expenses from the exports of
**any bank**, month by month.

- Imports PDF, CSV and Excel transaction lists without bank-specific rules (columns are recognised by their content);
  scanned or unstructured statements are read by Claude and converted to a canonical CSV.
- Merges overlapping exports into a single ledger without duplicates.
- Recognises merchants and maps bank categories to your own categories and subcategories.
- Tracks anomalies to verify and one-off (extraordinary) expenses.
- Compares recurring spending with the ISTAT averages for Italian households (optional).
- Generates three Markdown reports per month (main, statistics, details) in English or Italian.

## Privacy

All personal data stays in `data/`, which is excluded from git: bank files, ledger, rules, notes and reports.
The repository contains only generic code, invented test data and public ISTAT figures.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [uv](https://docs.astral.sh/uv/) (scripts declare their own dependencies)

## Usage

1. Copy `.claude/skills/family-budget/` into your project (or clone this repository).
2. Put your bank exports in `data/reports/`.
3. Ask Claude Code, for example: *"do the October report"*.

Claude follows the procedure in [`SKILL.md`](.claude/skills/family-budget/SKILL.md): import, merchants, categories,
one-offs and anomalies, reports in `data/YYYY-MM/`. Set the report language in `data/settings.json`:

```json
{"language": "it"}
```

## Development

```bash
uv sync
uv run pytest          # unit tests + an end-to-end month in Italian and English
uv run flake8 .claude tests && uv run mypy .claude/skills/family-budget/scripts --ignore-missing-imports
```
