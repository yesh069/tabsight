# How tabsight thinks

## The six rules

Every feature follows these rules. They are also tested automatically.

1. **Never change the user's data.** Every function works on a copy. A test calls every public function and checks that the input DataFrame is identical afterwards.
2. **A smart default, but always overridable.** Every guess can be changed in one argument (`overrides=`, `agg=`, `dayfirst=`, `unit=` ...).
3. **Warn, don't block.** Problems show up as warnings, not errors, unless you ask for strict mode (`ts.set_defaults(strict=True)`).
4. **Show every guess.** Profiles list a reason for every decision; results carry `notes`.
5. **Extras are opt-in.** Cleaning, forecasts and insights are off or clearly labelled.
6. **Private and offline by default.** No network calls, no telemetry, no clock.

## Reading vs cleaning

tabsight separates *understanding* data from *changing* it.

| | Reading (always on) | Cleaning (optional) |
|---|---|---|
| What it does | Works out roles, units and formats so results are right | Changes values: trims spaces, merges spellings, converts types |
| Changes your data? | No. It works on a temporary internal copy | Only in a new copy, with a report you can undo |
| Example | Reads `"01/15/2017"` as a date for grouping | Turns `west` into `West` |

## Roles

`ts.profile` gives every column one role:

| Role | Meaning | Example |
|------|---------|---------|
| `dimension` | Something you group by | Region, Category, Segment |
| `measure` | Something you add up or average | Sales, Profit, Discount |
| `time` | Dates and times (or whole-number years) | Order_Date, Year |
| `id` | Identifiers; counted, never summed | Order_ID, Postal_Code |
| `coord` | Latitude or longitude | Latitude, Lng |
| `text` | Long free text | Comments |

## Exact numbers after filtering

Dashboards let viewers filter. Re-adding sums after a filter is easy, but you cannot average averages, and a median of medians is wrong. tabsight therefore stores every aggregation as **parts** that can be re-combined exactly:

| Aggregation | Stored | Re-combined as |
|-------------|--------|----------------|
| sum | sum | sum of sums |
| mean | sum + count | total sum ÷ total count |
| weighted average | Σ(w·x) and Σw | Σ(w·x) ÷ Σw |
| median, distinct count | the values | computed from the values |

A property-based test generates random datasets and filters and checks that re-combined parts always equal pandas computing from the raw rows. See [Aggregating](../guide/aggregating.md).

## Determinism

The same input always gives the same output: no randomness, no reading of the clock ("today" comes from the data or `as_of=`), and ties are broken by name.
