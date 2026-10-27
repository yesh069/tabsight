# Locales and currencies

## Locales

Examples: `1234.5` as currency with 2 decimals, `123456.7` as a number with 1 decimal, `2,300,000` as compact currency, and 5 January 2017 as a day. This table is checked against the code by `tests/test_docs.py`.

| Locale | Currency | Currency example | Number example | Compact | Date |
|--------|----------|------------------|----------------|---------|------|
| `en_US` | `USD` | `$1,234.50` | `123,456.7` | `$2.3M` | Jan 5, 2017 |
| `en_GB` | `GBP` | `£1,234.50` | `123,456.7` | `£2.3M` | 5 Jan 2017 |
| `en_IE` | `EUR` | `€1,234.50` | `123,456.7` | `€2.3M` | 5 Jan 2017 |
| `en_AU` | `AUD` | `$1,234.50` | `123,456.7` | `$2.3M` | 5 Jan 2017 |
| `en_CA` | `CAD` | `$1,234.50` | `123,456.7` | `$2.3M` | Jan 5, 2017 |
| `en_IN` | `INR` | `₹1,234.50` | `1,23,456.7` | `₹23L` | 5 Jan 2017 |
| `de_DE` | `EUR` | `1.234,50 €` | `123.456,7` | `2,3 Mio. €` | 5 Jan. 2017 |
| `de_AT` | `EUR` | `€ 1 234,50` | `123 456,7` | `€ 2,3 Mio.` | 5 Jan. 2017 |
| `fr_FR` | `EUR` | `1 234,50 €` | `123 456,7` | `2,3 M €` | 5 janv. 2017 |
| `es_ES` | `EUR` | `1.234,50 €` | `123.456,7` | `2,3 M €` | 5 ene 2017 |
| `it_IT` | `EUR` | `1.234,50 €` | `123.456,7` | `2,3 Mln €` | 5 gen 2017 |
| `nl_NL` | `EUR` | `€ 1.234,50` | `123.456,7` | `€ 2,3 mln.` | 5 jan 2017 |
| `pt_BR` | `BRL` | `R$ 1.234,50` | `123.456,7` | `R$ 2,3 mi` | 5 jan 2017 |
| `pt_PT` | `EUR` | `1 234,50 €` | `123 456,7` | `2,3 M €` | 5 jan 2017 |

The spaces in these formats are non-breaking spaces, so a number never splits across two lines. Indian compact numbers use lakh (L = 100,000) and crore (Cr = 10,000,000).

A two-letter language code (`"de"`) uses that language's main locale. An unknown locale falls back with a `FormatWarning`. Right-to-left languages are not supported yet.

## Currency symbols

| Code | Symbol | Code | Symbol | Code | Symbol |
|------|--------|------|--------|------|--------|
| `USD` | $ | `EUR` | € | `GBP` | £ |
| `INR` | ₹ | `JPY` | ¥ | `CNY` | CN¥ |
| `AUD` | A$ | `CAD` | CA$ | `CHF` | CHF |
| `BRL` | R$ | `KRW` | ₩ | `RUB` | ₽ |
| `MXN` | MX$ | `SGD` | S$ | `HKD` | HK$ |
| `NZD` | NZ$ | `ZAR` | R | `SEK` | kr |
| `NOK` | kr | `DKK` | kr | `PLN` | zł |
| `TRY` | ₺ | `ILS` | ₪ | `THB` | ฿ |
| `NGN` | ₦ | `PHP` | ₱ | `VND` | ₫ |

Any other valid 3-letter code is shown before the number (`XYZ 10.00`). `JPY`, `KRW`, `VND`, `CLP`, `ISK` and `HUF` use no decimals.

## Translations

Month and weekday names: English, German, French, Spanish, Italian, Dutch and Portuguese. Interface words ("Other", "No data"...) are English for now; other languages can be added as small JSON files in `src/tabsight/i18n/`.
