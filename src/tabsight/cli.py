"""Command line: ``tabsight auto sales.csv -o sales.html`` and friends.

Commands:

- ``auto FILE``: a whole dashboard chosen from the data (``ts.auto``)
- ``chart FILE KIND``: one chart (``ts.chart``), as HTML or a still SVG/PNG picture
- ``build SPEC FILE``: a saved dashboard (``dash.save``) drawn on new data
- ``serve FILE``: a dashboard in server mode on this computer (standard library only)
- ``profile`` / ``check`` / ``clean`` / ``recommend FILE``: the data tools

Files are read with ``ts.load`` (CSV, TSV, Excel, Parquet, JSON) and written only where
``-o`` says; an output never overwrites the input file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from tabsight._version import __version__
from tabsight.warnings import TabsightError


def _read(path: str, sheet: str | None = None) -> Any:
    from tabsight.io import load

    return load(path, sheet=sheet)


def _out(args: argparse.Namespace, default_suffix: str) -> Path:
    src = Path(args.file).resolve()
    out = Path(args.output) if args.output else src.with_suffix(default_suffix)
    if out.resolve() == src:
        raise TabsightError("the output would overwrite the input file; pass a different -o")
    return out


def _say(args: argparse.Namespace, text: str) -> None:
    if not getattr(args, "quiet", False):
        print(text)


def _settings(args: argparse.Namespace) -> dict[str, Any]:
    return {k: getattr(args, k) for k in ("theme", "locale", "currency") if getattr(args, k, None)}


# ---------------------------------------------------------------- commands


def _auto(args: argparse.Namespace) -> int:
    from tabsight.auto import auto

    df = _read(args.file, args.sheet)
    title = args.title or Path(args.file).stem.replace("_", " ").replace("-", " ").strip().title()
    dash = auto(
        df, title, max_tiles=args.max_tiles, insights=not args.no_insights, **_settings(args)
    )
    out = _out(args, ".html")
    dash.to_html(out, cdn=args.cdn)
    if args.save:
        dash.save(args.save)
        _say(args, f"saved the dashboard spec to {args.save}")
    for line in dash.decisions:
        _say(args, f"  {line}")
    _say(args, f"wrote {out} ({len(dash.tiles)} tiles)")
    return 0


def _chart(args: argparse.Namespace) -> int:
    from tabsight.charts import chart

    df = _read(args.file, args.sheet)
    kwargs: dict[str, Any] = {k: getattr(args, k) for k in ("x", "y", "color", "geo", "freq", "agg", "title")
                              if getattr(args, k) is not None}  # fmt: skip
    if args.top is not None:
        kwargs["top"] = args.top
    fig = chart(df, args.kind, **kwargs, **_settings(args))
    out = _out(args, ".html")
    suffix = out.suffix.lower()
    if suffix == ".svg":
        fig.to_svg(out)
    elif suffix == ".png":
        fig.to_png(out, scale=args.scale)
    else:
        fig.to_html(out, cdn=args.cdn)
    for issue in fig.lint():
        _say(args, f"  lint: {issue}")
    _say(args, f"wrote {out}")
    return 0


def _datasets(pairs: list[str], sheet: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name or not path:
            raise TabsightError(f"--data takes NAME=FILE, not {pair!r}")
        out[name] = _read(path, sheet)
    return out


def _build(args: argparse.Namespace) -> int:
    from tabsight.dashboard import Dashboard

    dash = Dashboard.load(args.spec).bind(
        _read(args.file, args.sheet), **_datasets(args.data, args.sheet)
    )
    out = _out(args, ".html")
    dash.to_html(out, cdn=args.cdn)
    _say(args, f"wrote {out} ({len(dash.tiles)} tiles)")
    return 0


def _serve(args: argparse.Namespace) -> int:
    from tabsight.dashboard import Dashboard

    df = _read(args.file, args.sheet)
    if args.spec:
        dash = Dashboard.load(args.spec).bind(df, **_datasets(args.data, args.sheet))
    else:
        from tabsight.auto import auto

        dash = auto(
            df, args.title or Path(args.file).stem.replace("_", " ").title(), **_settings(args)
        )
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"warning: listening on {args.host} lets other computers see this data", file=sys.stderr
        )
    from tabsight.localserver import serve

    serve(dash, host=args.host, port=args.port, quiet=args.quiet)
    return 0


def _profile(args: argparse.Namespace) -> int:
    from tabsight.profile import profile

    print(profile(_read(args.file, args.sheet), quiet=True).show())
    return 0


def _check(args: argparse.Namespace) -> int:
    from tabsight.check import check

    report = check(_read(args.file, args.sheet))
    print(report.show())
    return 1 if any(i.severity == "error" for i in report.issues) else 0


def _clean(args: argparse.Namespace) -> int:
    from tabsight.clean import clean

    cleaned, report = clean(_read(args.file, args.sheet), args.mode, dedupe=args.dedupe)
    out = _out(args, ".clean.csv")
    if out.suffix.lower() == ".parquet":
        cleaned.to_parquet(out, index=False)
    else:
        cleaned.to_csv(out, index=False)
    _say(args, report.show())
    _say(args, f"wrote {out}")
    return 0


def _recommend(args: argparse.Namespace) -> int:
    from tabsight.recommend import recommend

    print(recommend(_read(args.file, args.sheet), x=args.x, y=args.y, color=args.color).show())
    return 0


# ---------------------------------------------------------------- the parser


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tabsight",
        description="BI-quality charts, maps and dashboards from a data file. Rule-based, offline.",
    )
    parser.add_argument("--version", action="version", version=f"tabsight {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def command(
        name: str, help: str, func: Any, *, output: bool = False, style: bool = False
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help, description=help)
        p.set_defaults(func=func)
        if name != "build":
            p.add_argument("file", help="CSV, TSV, Excel, Parquet or JSON file")
        p.add_argument("--sheet", help="Excel sheet name")
        if output:
            p.add_argument("-o", "--output", help="where to write (default: next to the input)")
            p.add_argument("-q", "--quiet", action="store_true", help="print nothing but errors")
        if style:
            p.add_argument("--theme", help="light, dark or print")
            p.add_argument("--locale", help="for example en_IE or de_DE")
            p.add_argument("--currency", help="for example EUR")
            p.add_argument(
                "--cdn", action="store_true", help="load ECharts from jsDelivr (smaller file)"
            )
        return p

    p = command("auto", "make a whole dashboard from a data file", _auto, output=True, style=True)
    p.add_argument("--title", help="dashboard title (default: from the file name)")
    p.add_argument("--max-tiles", type=int, default=10, help="most tiles to add (default 10)")
    p.add_argument("--no-insights", action="store_true", help="leave out the insights panel")
    p.add_argument(
        "--save",
        metavar="SPEC.json",
        help="also save the dashboard spec (no data) to reuse with build",
    )

    p = command(
        "chart",
        "draw one chart (.html, .svg or .png by the -o suffix)",
        _chart,
        output=True,
        style=True,
    )
    p.add_argument("kind", help="bar, line, map, donut, scatter... or auto")
    for name in ("x", "y", "color", "geo", "freq", "agg", "title"):
        p.add_argument(f"--{name}")
    p.add_argument("--top", type=int)
    p.add_argument("--scale", type=float, default=2.0, help="PNG pixel scale (default 2)")

    p = command(
        "build", "draw a saved dashboard spec on new data", _build, output=True, style=False
    )
    p.add_argument("spec", help="dashboard spec saved with dash.save() or auto --save")
    p.add_argument("file", help="the data")
    p.add_argument(
        "--data",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="data for tiles with their own",
    )
    p.add_argument("--cdn", action="store_true", help="load ECharts from jsDelivr (smaller file)")

    p = command("serve", "show a dashboard in server mode on this computer", _serve, style=True)
    p.add_argument("--spec", help="a saved dashboard spec (default: ts.auto)")
    p.add_argument(
        "--data",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="data for tiles with their own",
    )
    p.add_argument("--title")
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to listen on (default 127.0.0.1: this computer only)",
    )
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("-q", "--quiet", action="store_true", help="don't log each request")

    command("profile", "show what tabsight thinks each column is", _profile)
    command("check", "report data-quality issues (exit code 1 if any are errors)", _check)
    p = command("clean", "write a cleaned copy (.csv or .parquet)", _clean, output=True)
    p.add_argument(
        "--mode", default="safe", choices=["safe", "auto"], help="how much to fix (default safe)"
    )
    p.add_argument("--dedupe", action="store_true", help="also drop duplicate rows")
    p = command("recommend", "rank the charts that fit some columns", _recommend)
    p.add_argument("--x", action="append", help="column to group by (repeat for more)")
    p.add_argument("--y", action="append", help="measure column (repeat for more)")
    p.add_argument("--color")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except (TabsightError, OSError) as e:
        print(f"tabsight: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
