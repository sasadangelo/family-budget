# ISTAT reference averages

Public data to compare a household's spending with the Italian average (ISTAT is the Italian national statistics
institute). Update when ISTAT publishes a new edition (usually in October, with the previous year's data).
Numbers keep the source's Italian format: `2.782,36` = 2782.36. ISTAT item names are kept in Italian because
`istat-2025.json` and `data/benchmark.json` use them as keys.

## 1. Average monthly household spending: year 2025

Source: ISTAT, *Spese per consumi delle famiglie – Anno 2025* (published October 2026),
<https://www.istat.it/comunicato-stampa/spese-per-consumi-delle-famiglie-anno-2025/>.
Euro per month, current prices.

### Italy

| Indicator | 2024 | 2025 |
|---|---:|---:|
| Mean spending | 2.755,09 | 2.782,36 |
| Median spending | 2.239,62 | 2.337,57 |
| Food and non-alcoholic beverages | 532,85 | 552,06 |
| Non-food | 2.222,23 | 2.230,31 |

### By macro-area and region (mean spending)

| Area | 2024 | 2025 |
|---|---:|---:|
| Nord-ovest | 2.972,58 | 2.974,07 |
| Nord-est | 3.032,40 | 3.086,67 |
| Centro | 2.999,17 | 3.052,18 |
| Sud | 2.198,61 | 2.215,48 |
| Isole | 2.321,25 | 2.338,13 |
| Piemonte | 2.622,73 | 2.781,31 |
| Valle d'Aosta | 3.055,20 | 3.190,55 |
| Liguria | 2.763,36 | 2.915,39 |
| Lombardia | 3.162,32 | 3.066,39 |
| Trentino-Alto Adige | 3.584,09 | 3.444,26 |
| Veneto | 2.862,76 | 2.953,71 |
| Friuli-Venezia Giulia | 3.017,75 | 3.023,17 |
| Emilia-Romagna | 3.084,68 | 3.159,06 |
| Toscana | 3.160,39 | 3.108,13 |
| Umbria | 2.640,15 | 3.257,41 |
| Marche | 2.463,12 | 3.083,74 |
| Lazio | 3.081,27 | 2.979,50 |
| Abruzzo | 2.620,58 | 2.769,93 |
| Molise | 2.615,03 | 2.612,77 |
| Campania | 2.246,46 | 2.282,33 |
| Puglia | 1.999,72 | 1.974,56 |
| Basilicata | 2.324,17 | 2.323,45 |
| Calabria | 2.074,77 | 2.041,97 |
| Sicilia | 2.366,38 | 2.304,98 |
| Sardegna | 2.195,11 | 2.430,83 |

Regional means have sampling errors of 1-5% (Umbria 2025: 12%).

### By type of municipality

| Municipality type | 2024 | 2025 |
|---|---:|---:|
| Metropolitan area centre (e.g. the city of Rome) | 2.998,95 | 2.991,26 |
| Metropolitan suburbs and municipalities > 50,000 inhabitants | 2.822,26 | 2.804,44 |
| Other municipalities up to 50,000 inhabitants | 2.638,08 | 2.704,30 |

ISTAT does not publish averages for single municipalities.

### By household size and type

The labels are the keys of `households` in `istat-2025.json` (e.g. `Coppia con 2 figli` = couple with 2 children).

| Household | 2024 | 2025 |
|---|---:|---:|
| 1 componente | 1.931,70 | 2.070,43 |
| 2 componenti | 2.855,92 | 2.895,94 |
| 3 componenti | 3.325,15 | 3.306,02 |
| 4 componenti | 3.726,84 | 3.582,58 |
| 5 e più componenti | 3.618,61 | 3.578,53 |
| Coppia con 1 figlio | 3.446,13 | 3.431,15 |
| Coppia con 2 figli | 3.805,38 | 3.618,44 |
| Coppia con 3 e più figli | 3.683,93 | 3.633,07 |
| Monogenitore | 2.623,60 | 2.746,41 |
| Coppia senza figli, p.r. 35-64 anni | 3.139,15 | 3.187,03 |

### By expense item (Italy, all households)

| Item (COICOP 2018) | 2024 | 2025 |
|---|---:|---:|
| Prodotti alimentari e bevande analcoliche | 532,85 | 552,06 |
| Bevande alcoliche e tabacchi | 43,30 | 42,27 |
| Abbigliamento e calzature | 102,55 | 105,40 |
| Abitazione, acqua, elettricità, gas e altri combustibili | 984,42 | 1.000,80 |
| &nbsp;&nbsp;of which imputed rents (Affitti figurativi) | 617,39 | 611,44 |
| &nbsp;&nbsp;of which renovation work | 32,92 | 37,19 |
| Mobili, articoli e servizi per la casa | 115,10 | 114,39 |
| Salute | 116,22 | 113,18 |
| Trasporti | 297,22 | 294,06 |
| Informazione e comunicazione | 72,03 | 70,82 |
| Ricreazione, sport e cultura | 104,96 | 105,31 |
| Istruzione | 17,31 | 16,99 |
| Servizi di ristorazione e di alloggio | 161,91 | 163,67 |
| Servizi assicurativi e finanziari | 73,18 | 71,52 |
| Cura della persona, protezione sociale e altri beni e servizi | 134,02 | 131,89 |

ISTAT does not publish the items by household size. A rough estimate: multiply each item by the ratio between the
household type's total spending and the Italian average (e.g. 4 members: 3.582,58 / 2.782,36 ≈ 1.29). Food grows
more than proportionally with the number of members, housing less.

## 2. Regional price levels: year 2022

Source: ISTAT, *Indici spaziali dei prezzi al consumo* (experimental, published 21 October 2024),
<https://www.istat.it/wp-content/uploads/2024/10/Risultati-e-nota-metodologica.pdf>.
Italy = 100. It covers only five items: food, beverages, clothing, furnishings and household, restaurants and
accommodation. It does **not** cover housing (rents, energy) or transport.

### Aggregate index of the five items

| Region | Index | Region | Index |
|---|---:|---|---:|
| Alto Adige | 109,47 | Friuli-V.G. | 100,23 |
| Lombardia | 108,09 | Marche | 99,64 |
| Trentino | 106,17 | Lazio | 99,03 |
| Emilia-Romagna | 103,67 | Umbria | 97,69 |
| Toscana | 103,14 | Puglia | 97,67 |
| Liguria | 102,89 | Calabria | 97,50 |
| Veneto | 102,53 | Sicilia | 95,78 |
| Piemonte | 101,64 | Molise | 95,12 |
| Sardegna | 101,44 | Abruzzo | 94,51 |
| Valle d'Aosta | 101,41 | Basilicata | 92,69 |
| | | Campania | 91,82 |

### Lazio by item

| Item | Index |
|---|---:|
| Food | 101,82 |
| Non-alcoholic beverages | 101,63 |
| Clothing and footwear | 93,78 |
| Furnishings and household services | 97,87 |
| Restaurants and accommodation | 99,25 |

For the other regions by item see charts 2-7 of the document.

## 3. How to compare correctly

- **Imputed rent**: for home owners ISTAT spending includes an "imputed" rent (611 € per month on average in 2025),
  which is not an actual outflow. To compare with real expenses:
  - *owners with a mortgage*: remove imputed rent from the ISTAT average and mortgage installments from expenses, or
    keep both (installment as rent equivalent);
  - *tenants*: the rent paid corresponds to the housing item, no correction needed.
- **Loan installments**: not consumption for ISTAT (the good is counted when bought). Exclude them from expenses.
- **One-off expenses**: ISTAT averages include them, spread over the year. On a single month compare both with and
  without them; a reliable comparison needs at least 3-6 months.
- **Area**: use the average of the region or municipality type; price levels (section 2) tell whether higher spending
  comes from prices or from quantities.
- **Mean or median**: the Italian median (2.338 €) is lower than the mean (2.782 €); most households spend less than
  the mean.
