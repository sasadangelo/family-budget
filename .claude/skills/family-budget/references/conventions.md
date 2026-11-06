# Input conventions

## Canonical format (the ledger)

UTF-8 CSV with header, one row per transaction:

```
date,description,amount,currency,category,account,source_file
2026-03-14,Supermercato Esempio Via Lunga 1,-37.80,EUR,Groceries,,list_march.pdf
2026-03-27,Salary,2500.00,EUR,Salary,,list_march.pdf
```

| Column | Required | Rule |
|---|---|---|
| `date` | yes | `YYYY-MM-DD` |
| `description` | yes | the bank's text as is (spaces and line breaks collapsed) |
| `amount` | yes | decimal point, **signed**: negative = expense, positive = income |
| `currency` | no | ISO 4217, default `EUR` |
| `category` | no | the bank's category, if any |
| `account` | no | label of the account/card (`--account`) |
| `source_file` | no | file the transaction comes from |

Two transactions are the same transaction when date, amount and description (case-insensitive) are equal.
Identical transactions repeated in the same file (two equal top-ups on the same day) stay distinct: the merge keeps
the maximum number of occurrences between ledger and new file, not the sum.

## Input levels, from simplest to most complex

| Level | Input | How it is read |
|---|---|---|
| 0 | CSV already canonical | read directly |
| 1 | CSV/TSV (any delimiter and encoding) or Excel `.xlsx` | columns recognised by their content |
| 2 | PDF with text tables | table extraction (ruling lines, then text alignment), then as level 1 |
| 3 | scans, photos, free text | Claude reads the document and writes a canonical CSV (level 0) |

## How columns are recognised (levels 1-2)

No per-bank rules. The script:

1. groups tables with the same number of columns (one table split across pages);
2. treats as **data rows** those with at least one date and one amount; the others are headers or noise;
3. classifies each column by content (≥ 80% of the cells): dates, amounts or text;
4. **date** = the first date column (booking/operation date comes before the value date);
5. **amount**: a single amount column is already signed; with two (debit/credit) they are told apart by generic header
   keywords (`dare/uscite/addebiti/debit` vs `avere/entrate/accrediti/credit`); balance columns (`saldo/balance`) are
   ignored;
6. **category** = text column whose header contains `categ`;
7. **description** = text column with a descriptive header (`descrizione/operazione/causale/details`…), otherwise the
   longest text column;
8. **day/month** order: inferred from the values (a first number > 12 is the day); when ambiguous, day/month.

Accepted amounts: `€ -1.234,56`, `-1,234.56`, `1234.5`, `1.234`, `-37,80 EUR`.

When the layout is ambiguous the script stops with an explicit error instead of guessing.

## Merchants

The merchant is derived from the description in two steps:

1. generic clean-up: removes transaction-type prefixes (`Addebito diretto disposto a favore di:`,
   `Bonifico disposto da:`, `Pagamento`, `Payment to`…), payment-processor prefixes (`Paypal *`, `SumUp *`…),
   mandates and references, codes after `*`, street addresses (`Via …`, `Viale …`, `Street …`, also truncated), words
   containing digits;
2. the user's private rules in `data/`:
   - `merchant_stopwords.txt`: one word per line, removed from the **end** of the name (cities, countries);
   - `merchants.csv`: `pattern,merchant`; the pattern is a case-insensitive substring, or a regex between slashes
     (`/^negozio esempio$/`); it is matched against both the cleaned name and the raw description; the first matching
     row wins.

## Reversals

In the report, a reversal (positive transaction with `storn`, `rimbors`, `refund`, `reversal`, `chargeback` or
`annull` in category or description) cancels the closest payment of exactly the opposite amount, made on the same day
or within the previous 60 days. Both are excluded. A reversal without a matching payment stays. Two opposite
transactions without reversal keywords (e.g. a transfer received and one sent) do not cancel each other.
