# Formula functions

Every function available in [calculated fields](../guide/calculated-fields.md). Names are not case-sensitive. Nothing outside this list can be called.

## Aggregates

An aggregate makes the whole formula an *aggregate formula* (computed after grouping). Aggregates take one argument and cannot be nested.

| Function | Meaning |
|----------|---------|
| `SUM(x)` | Total |
| `AVG(x)` | Average of the values present |
| `MIN(x)` | Smallest value |
| `MAX(x)` | Largest value |
| `COUNT(x)` | Number of values present |
| `COUNTD(x)` | Number of distinct values |
| `MEDIAN(x)` | Middle value |

`MIN(a, b)` and `MAX(a, b)` with **two** arguments are row-level: the smaller or larger of two values in each row.

## Numbers

| Function | Meaning |
|----------|---------|
| `ABS(x)` | Absolute value |
| `ROUND(x)` / `ROUND(x, digits)` | Round (digits from -10 to 10) |
| `FLOOR(x)`, `CEILING(x)` | Round down, round up |
| `SQRT(x)` | Square root (missing for negative x) |
| `LN(x)` | Natural logarithm (missing for x ≤ 0) |
| `LOG(x)` / `LOG(x, base)` | Logarithm, base 10 by default |
| `EXP(x)` | e to the power x |
| `POWER(x, y)` | x to the power y |
| `SIGN(x)` | -1, 0 or 1 |
| `FLOAT(x)` | As a number |
| `INT(x)` | Whole-number part |

Results that overflow or are undefined become missing values, never infinity.

## Missing values

| Function | Meaning |
|----------|---------|
| `ZN(x)` | x, or 0 when missing |
| `IFNULL(x, y)` | x, or y when x is missing |
| `ISNULL(x)` | TRUE when x is missing |

## Text

| Function | Meaning |
|----------|---------|
| `LEN(s)` | Number of characters |
| `UPPER(s)`, `LOWER(s)` | Change case |
| `TRIM(s)` | Remove spaces at both ends |
| `CONTAINS(s, 'text')` | TRUE when s contains the text (plain text, not a pattern) |
| `STARTSWITH(s, 'text')`, `ENDSWITH(s, 'text')` | Starts or ends with the text |
| `LEFT(s, n)`, `RIGHT(s, n)` | First or last n characters (n up to 10,000) |

`+` joins text: `[City] + ', ' + [State]`.

## Dates

| Function | Meaning |
|----------|---------|
| `YEAR(d)` | Year |
| `QUARTER(d)` | Quarter 1–4 |
| `MONTH(d)` | Month 1–12 |
| `DAY(d)` | Day of the month |
| `WEEKDAY(d)` | 1 = Monday … 7 = Sunday |
| `DATEDIFF('unit', start, end)` | Whole units from start to end; unit is `'day'`, `'week'`, `'month'`, `'quarter'` or `'year'` |

## Logic

`IF cond THEN value ELSEIF cond THEN value ELSE value END`, with `AND`, `OR`, `NOT`, comparisons (`=` `<>` `<` `<=` `>` `>=`), `TRUE`, `FALSE` and `NULL`.

## Limits

| Limit | Value |
|-------|-------|
| Formula length | 2,000 characters |
| Parts (numbers, names, operators) | 1,000 |
| Nesting depth | 50 |
| Text value length | 500 characters |
| Parameters per call | 100 |
