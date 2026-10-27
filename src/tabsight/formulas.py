"""Calculated fields: ``ts.calc("Margin = SUM(Profit) / SUM(Sales)")``.

A small formula language with our own tokenizer, parser and interpreter. It never uses
``eval``/``exec``, never looks up attributes, and only knows the functions listed in
``FUNCTIONS``. Formulas are limited in length, token count and nesting depth, so a
hostile formula cannot hang or crash the process.

Two levels, as in Tableau:

- **row-level** (``[Profit] / [Sales]``): computed for every row, then aggregated.
- **aggregate** (``SUM([Profit]) / SUM([Sales])``): computed after grouping. Each
  aggregate inside becomes a hidden exact measure, so the result stays exact when a
  dashboard viewer filters.

Parameters are written ``$Name`` and supplied at evaluation time.
"""

from __future__ import annotations

import dataclasses
import difflib
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from tabsight.warnings import InvalidSpecError, safe_repr

__all__ = ["FUNCTIONS", "CalcError", "CalcField", "calc", "validate_params"]

MAX_LENGTH = 2000
MAX_TOKENS = 1000
MAX_DEPTH = 50
MAX_STRING = 500


class CalcError(InvalidSpecError):
    """A formula that cannot be parsed or evaluated."""


# ---------------------------------------------------------------- tokens

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,3})?)
  | (?P<str>'(?:[^'\x00-\x1f]|'')*'|"(?:[^"\x00-\x1f]|"")*")
  | (?P<field>\[[^\[\]\x00-\x1f]{1,200}\])
  | (?P<param>\$[A-Za-z_][A-Za-z0-9_]{0,63})
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]{0,199})
  | (?P<op><=|>=|<>|!=|==|[=<>+\-*/%(),])
    """,
    re.VERBOSE,
)
_KEYWORDS = {"IF", "THEN", "ELSEIF", "ELSE", "END", "AND", "OR", "NOT", "TRUE", "FALSE", "NULL"}


@dataclasses.dataclass(frozen=True)
class _Tok:
    kind: str
    value: str
    pos: int


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise CalcError(f"unexpected character {safe_repr(text[pos])} at position {pos + 1}")
        kind = m.lastgroup or ""
        value = m.group()
        if kind != "ws":
            if kind == "str" and len(value) - 2 > MAX_STRING:
                raise CalcError(
                    f"text value at position {pos + 1} is longer than {MAX_STRING} characters"
                )
            if kind == "ident" and value.upper() in _KEYWORDS:
                kind, value = "kw", value.upper()
            tokens.append(_Tok(kind, value, pos))
            if len(tokens) > MAX_TOKENS:
                raise CalcError(f"formula has more than {MAX_TOKENS} parts")
        pos = m.end()
    return tokens


# ---------------------------------------------------------------- syntax tree


@dataclasses.dataclass(frozen=True)
class Num:
    value: float


@dataclasses.dataclass(frozen=True)
class Str:
    value: str


@dataclasses.dataclass(frozen=True)
class Const:
    value: bool | None


@dataclasses.dataclass(frozen=True)
class FieldRef:
    name: str


@dataclasses.dataclass(frozen=True)
class ParamRef:
    name: str


@dataclasses.dataclass(frozen=True)
class Unary:
    op: str
    operand: Node


@dataclasses.dataclass(frozen=True)
class Binary:
    op: str
    left: Node
    right: Node


@dataclasses.dataclass(frozen=True)
class Call:
    fn: str
    args: tuple[Node, ...]


@dataclasses.dataclass(frozen=True)
class If:
    branches: tuple[tuple[Node, Node], ...]
    otherwise: Node | None


@dataclasses.dataclass(frozen=True, eq=False)
class _Lit:
    """An already-computed value placed back into the tree (used for aggregate formulas)."""

    value: Any


Node = Num | Str | Const | FieldRef | ParamRef | Unary | Binary | Call | If | _Lit

AGGREGATES = {
    "SUM": "sum",
    "AVG": "mean",
    "MIN": "min",
    "MAX": "max",
    "COUNT": "count",
    "COUNTD": "countd",
    "MEDIAN": "median",
}
# name: (min args, max args)
FUNCTIONS: dict[str, tuple[int, int]] = {
    **{name: (1, 1) for name in AGGREGATES},
    "ABS": (1, 1), "ROUND": (1, 2), "FLOOR": (1, 1), "CEILING": (1, 1), "SQRT": (1, 1),
    "LN": (1, 1), "LOG": (1, 2), "EXP": (1, 1), "POWER": (2, 2), "SIGN": (1, 1),
    "ZN": (1, 1), "IFNULL": (2, 2), "ISNULL": (1, 1), "FLOAT": (1, 1), "INT": (1, 1),
    "LEN": (1, 1), "UPPER": (1, 1), "LOWER": (1, 1), "TRIM": (1, 1),
    "CONTAINS": (2, 2), "STARTSWITH": (2, 2), "ENDSWITH": (2, 2), "LEFT": (2, 2), "RIGHT": (2, 2),
    "YEAR": (1, 1), "QUARTER": (1, 1), "MONTH": (1, 1), "DAY": (1, 1), "WEEKDAY": (1, 1),
    "DATEDIFF": (3, 3),
}  # fmt: skip
_COMPARE = {
    "=": "eq",
    "==": "eq",
    "<>": "ne",
    "!=": "ne",
    "<": "lt",
    "<=": "le",
    ">": "gt",
    ">=": "ge",
}


class _Parser:
    def __init__(self, tokens: list[_Tok], text: str) -> None:
        self.tokens = tokens
        self.i = 0
        self.depth = 0
        self.text = text

    def peek(self, offset: int = 0) -> _Tok | None:
        j = self.i + offset
        return self.tokens[j] if j < len(self.tokens) else None

    def take(self) -> _Tok:
        tok = self.peek()
        if tok is None:
            raise CalcError("formula ends too early")
        self.i += 1
        return tok

    def expect(self, kind: str, value: str | None = None) -> _Tok:
        if self.peek() is None:
            raise CalcError(f"expected {(value or kind)!r}, but the formula ends")
        tok = self.take()
        if tok.kind != kind or (value is not None and tok.value != value):
            want = value or kind
            raise CalcError(
                f"expected {want!r} at position {tok.pos + 1}, found {safe_repr(tok.value)}"
            )
        return tok

    def at(self, kind: str, *values: str) -> bool:
        tok = self.peek()
        return tok is not None and tok.kind == kind and (not values or tok.value in values)

    def enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise CalcError(f"formula is nested more than {MAX_DEPTH} levels deep")

    def parse(self) -> Node:
        node = self.expr()
        tok = self.peek()
        if tok is not None:
            raise CalcError(f"unexpected {safe_repr(tok.value)} at position {tok.pos + 1}")
        return node

    def expr(self) -> Node:
        self.enter()
        try:
            node = self.and_()
            while self.at("kw", "OR"):
                self.take()
                node = Binary("or", node, self.and_())
            return node
        finally:
            self.depth -= 1

    def and_(self) -> Node:
        node = self.not_()
        while self.at("kw", "AND"):
            self.take()
            node = Binary("and", node, self.not_())
        return node

    def not_(self) -> Node:
        if self.at("kw", "NOT"):
            self.take()
            self.enter()
            try:
                return Unary("not", self.not_())
            finally:
                self.depth -= 1
        return self.compare()

    def compare(self) -> Node:
        node = self.additive()
        if self.at("op", *_COMPARE):
            op = _COMPARE[self.take().value]
            node = Binary(op, node, self.additive())
        return node

    def additive(self) -> Node:
        node = self.term()
        while self.at("op", "+", "-"):
            op = self.take().value
            node = Binary(op, node, self.term())
        return node

    def term(self) -> Node:
        node = self.unary()
        while self.at("op", "*", "/", "%"):
            op = self.take().value
            node = Binary(op, node, self.unary())
        return node

    def unary(self) -> Node:
        if self.at("op", "-", "+"):
            op = self.take().value
            self.enter()
            try:
                operand = self.unary()
            finally:
                self.depth -= 1
            return Unary("neg", operand) if op == "-" else operand
        return self.primary()

    def primary(self) -> Node:
        tok = self.take()
        if tok.kind == "num":
            return Num(float(tok.value))
        if tok.kind == "str":
            quote = tok.value[0]
            return Str(tok.value[1:-1].replace(quote * 2, quote))
        if tok.kind == "field":
            return FieldRef(tok.value[1:-1])
        if tok.kind == "param":
            return ParamRef(tok.value[1:])
        if tok.kind == "kw":
            if tok.value in ("TRUE", "FALSE"):
                return Const(tok.value == "TRUE")
            if tok.value == "NULL":
                return Const(None)
            if tok.value == "IF":
                return self.if_()
            raise CalcError(f"unexpected {tok.value} at position {tok.pos + 1}")
        if tok.kind == "op" and tok.value == "(":
            node = self.expr()
            self.expect("op", ")")
            return node
        if tok.kind == "ident":
            if self.at("op", "("):
                return self.call(tok)
            return FieldRef(tok.value)
        raise CalcError(f"unexpected {safe_repr(tok.value)} at position {tok.pos + 1}")

    def call(self, name_tok: _Tok) -> Node:
        fn = name_tok.value.upper()
        if fn not in FUNCTIONS:
            hint = difflib.get_close_matches(fn, FUNCTIONS, n=1)
            extra = f"; did you mean {hint[0]}?" if hint else ""
            raise CalcError(f"unknown function {safe_repr(name_tok.value)}{extra}")
        self.expect("op", "(")
        args: list[Node] = []
        if not self.at("op", ")"):
            args.append(self.expr())
            while self.at("op", ","):
                self.take()
                args.append(self.expr())
        self.expect("op", ")")
        lo, hi = FUNCTIONS[fn]
        if fn in ("MIN", "MAX") and len(args) == 2:
            return Call(fn + "2", tuple(args))  # row-level smaller/larger of two values
        if not lo <= len(args) <= hi:
            want = str(lo) if lo == hi else f"{lo}-{hi}"
            raise CalcError(f"{fn} takes {want} argument(s), got {len(args)}")
        return Call(fn, tuple(args))

    def if_(self) -> Node:
        branches = [(self.expr(), self._then())]
        otherwise = None
        while self.at("kw", "ELSEIF"):
            self.take()
            branches.append((self.expr(), self._then()))
        if self.at("kw", "ELSE"):
            self.take()
            otherwise = self.expr()
        self.expect("kw", "END")
        return If(tuple(branches), otherwise)

    def _then(self) -> Node:
        self.expect("kw", "THEN")
        return self.expr()


# ---------------------------------------------------------------- analysis


def _walk(node: Node) -> list[Node]:
    out: list[Node] = [node]
    if isinstance(node, Unary):
        out += _walk(node.operand)
    elif isinstance(node, Binary):
        out += _walk(node.left) + _walk(node.right)
    elif isinstance(node, Call):
        for a in node.args:
            out += _walk(a)
    elif isinstance(node, If):
        for cond, val in node.branches:
            out += _walk(cond) + _walk(val)
        if node.otherwise is not None:
            out += _walk(node.otherwise)
    return out


def _check_levels(node: Node, inside_agg: bool = False) -> bool:
    """Return True if the node contains an aggregate. Rejects nesting and mixing."""
    if isinstance(node, Call) and node.fn in AGGREGATES:
        if inside_agg:
            raise CalcError(
                f"an aggregate cannot contain another aggregate ({node.fn} inside an aggregate)"
            )
        _check_levels(node.args[0], inside_agg=True)
        return True
    children: list[Node] = []
    if isinstance(node, Unary):
        children = [node.operand]
    elif isinstance(node, Binary):
        children = [node.left, node.right]
    elif isinstance(node, Call):
        children = list(node.args)
    elif isinstance(node, If):
        children = [n for pair in node.branches for n in pair] + (
            [node.otherwise] if node.otherwise else []
        )
    flags = [_check_levels(c, inside_agg) for c in children]
    has_agg = any(flags)
    if has_agg and not inside_agg:
        for c, flag in zip(children, flags, strict=True):
            if not flag and any(isinstance(n, FieldRef) for n in _walk(c)):
                raise CalcError(
                    "cannot mix aggregate and row-level values; wrap every field in an "
                    "aggregate such as SUM(...) or use none at all"
                )
    return has_agg


# ---------------------------------------------------------------- the CalcField


_NAME_RE = re.compile(r"[^\x00-\x1f\[\]]{1,200}")
_DEFINITION = re.compile(
    r"\s*(?:\[([^\[\]\x00-\x1f]{1,200})\]|([A-Za-z_][A-Za-z0-9_ ]{0,199}?))\s*=(?!=)(.*)", re.S
)


@dataclasses.dataclass(frozen=True)
class CalcField:
    name: str
    expression: str
    tree: Node
    level: str  # "row" or "aggregate"
    fields: tuple[str, ...]
    params: tuple[str, ...]

    @property
    def aggregates(self) -> tuple[Call, ...]:
        """Each aggregate call, once, in order of appearance."""
        seen: list[Call] = []
        for n in _walk(self.tree):
            if isinstance(n, Call) and n.fn in AGGREGATES and n not in seen:
                seen.append(n)
        return tuple(seen)

    @property
    def needs_server(self) -> bool:
        """Row-level formulas with parameters cannot be recomputed in an offline HTML file."""
        return self.level == "row" and bool(self.params)

    def check_fields(self, columns: Sequence[str]) -> None:
        for f in self.fields:
            if f not in columns:
                hint = difflib.get_close_matches(f, list(columns), n=1)
                extra = f"; did you mean [{hint[0]}]?" if hint else ""
                raise CalcError(f"{self.name}: column {safe_repr(f)} not found{extra}")

    def evaluate(self, data: pd.DataFrame, params: Mapping[str, Any] | None = None) -> pd.Series:
        """Row-level formulas only: one value per row."""
        if self.level != "row":
            raise CalcError(
                f"{self.name} is an aggregate formula; use it as a measure in ts.aggregate"
            )
        self.check_fields(list(data.columns))
        values = validate_params(params, self.params)
        out = _eval(self.tree, data, values, len(data))
        return _as_series(out, data.index).rename(self.name)


def calc(definition: str, *, name: str | None = None) -> CalcField:
    """Parse ``"Name = formula"`` (or a formula plus ``name=``) into a CalcField."""
    if not isinstance(definition, str):
        raise CalcError("a formula must be text")
    if len(definition) > MAX_LENGTH:
        raise CalcError(f"formula is longer than {MAX_LENGTH} characters")
    expression = definition
    if name is None:
        m = _DEFINITION.fullmatch(definition)
        if m is None:
            raise CalcError("write it as 'Name = formula', or pass name=")
        name = (m.group(1) or m.group(2) or "").strip()
        expression = m.group(3)
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise CalcError(f"calculated field name {safe_repr(name)} is not allowed")
    tree = _Parser(_tokenize(expression), expression).parse()
    level = "aggregate" if _check_levels(tree) else "row"
    nodes = _walk(tree)
    fields = tuple(dict.fromkeys(n.name for n in nodes if isinstance(n, FieldRef)))
    params = tuple(dict.fromkeys(n.name for n in nodes if isinstance(n, ParamRef)))
    return CalcField(name, expression.strip(), tree, level, fields, params)


def validate_params(params: Mapping[str, Any] | None, needed: Sequence[str] = ()) -> dict[str, Any]:
    params = dict(params or {})
    if len(params) > 100:
        raise CalcError("too many parameters")
    for key, value in params.items():
        if not (isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", key)):
            raise CalcError(f"parameter name {safe_repr(key)} is not allowed")
        if isinstance(value, str):
            if len(value) > MAX_STRING:
                raise CalcError(f"parameter {key} is too long")
        elif not (
            isinstance(value, bool | int | float)
            and (not isinstance(value, float) or np.isfinite(value))
        ):
            raise CalcError(f"parameter {key} must be a number, text or true/false")
    missing = [p for p in needed if p not in params]
    if missing:
        raise CalcError(f"missing parameter value(s): {', '.join('$' + p for p in missing)}")
    return params


# ---------------------------------------------------------------- evaluation

Value = Any  # a pandas Series or a scalar


def _as_series(value: Value, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(
        [value] * len(index), index=index, dtype="object" if isinstance(value, str) else None
    )


def _numeric(value: Value, what: str) -> Value:
    if isinstance(value, pd.Series):
        if pd.api.types.is_bool_dtype(value):
            return value.astype("float64")
        if not pd.api.types.is_numeric_dtype(value):
            converted = pd.to_numeric(value, errors="coerce")
            if converted.notna().sum() < value.notna().sum():
                raise CalcError(f"{what} needs numbers, but got text")
            return converted.astype("float64")
        return value.astype("float64")
    if value is None:
        return np.nan
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    raise CalcError(f"{what} needs numbers, but got text")


def _clean(value: Value) -> Value:
    """Infinite results (overflow, log of 0) become missing, like division by zero."""
    if isinstance(value, pd.Series) and pd.api.types.is_float_dtype(value):
        return value.where(np.isfinite(value))
    if isinstance(value, float) and not np.isfinite(value):
        return np.nan
    return value


def _eval(node: Node, data: pd.DataFrame, params: Mapping[str, Any], n: int) -> Value:
    if isinstance(node, _Lit):
        return node.value
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Str):
        return node.value
    if isinstance(node, Const):
        return np.nan if node.value is None else node.value
    if isinstance(node, FieldRef):
        return data[node.name]
    if isinstance(node, ParamRef):
        return params[node.name]
    if isinstance(node, Unary):
        v = _eval(node.operand, data, params, n)
        if node.op == "neg":
            return -_numeric(v, "minus")
        return ~_as_series(v, data.index).astype("boolean").fillna(False)
    if isinstance(node, Binary):
        return _binary(node, data, params, n)
    if isinstance(node, If):
        result = _as_series(
            _eval(node.otherwise, data, params, n) if node.otherwise is not None else np.nan,
            data.index,
        )
        for cond, val in reversed(node.branches):
            c = _as_series(_eval(cond, data, params, n), data.index).astype("boolean").fillna(False)
            v = _as_series(_eval(val, data, params, n), data.index)
            result = v.where(c.astype(bool), result)
        return result
    if isinstance(node, Call):
        return _call(node, data, params, n)
    raise CalcError("unsupported formula element")  # pragma: no cover


def _binary(node: Binary, data: pd.DataFrame, params: Mapping[str, Any], n: int) -> Value:
    a = _eval(node.left, data, params, n)
    b = _eval(node.right, data, params, n)
    op = node.op
    if op in ("and", "or"):
        sa = _as_series(a, data.index).astype("boolean").fillna(False)
        sb = _as_series(b, data.index).astype("boolean").fillna(False)
        return (sa & sb) if op == "and" else (sa | sb)
    if op in ("eq", "ne", "lt", "le", "gt", "ge"):
        sa = _as_series(a, data.index)
        return getattr(sa, op)(b)
    if op == "+" and (_is_text(a) or _is_text(b)):
        return _as_series(a, data.index).astype("string") + _as_series(b, data.index).astype(
            "string"
        )
    x, y = _numeric(a, op), _numeric(b, op)
    with np.errstate(all="ignore"):
        if op == "+":
            return _clean(x + y)
        if op == "-":
            return _clean(x - y)
        if op == "*":
            return _clean(x * y)
        if op == "/":
            return _clean(_divide(x, y))
        return _clean(_divide(x, y, mod=True))


def _divide(x: Value, y: Value, mod: bool = False) -> Value:
    ys = (
        y
        if isinstance(y, pd.Series)
        else pd.Series(y, index=x.index)
        if isinstance(x, pd.Series)
        else y
    )
    if isinstance(ys, pd.Series):
        safe = ys.where(ys != 0)
        return (x % safe) if mod else (x / safe)
    if ys == 0:
        return np.nan
    return (x % ys) if mod else (x / ys)


def _is_text(v: Value) -> bool:
    if isinstance(v, str):
        return True
    return bool(
        isinstance(v, pd.Series)
        and (pd.api.types.is_string_dtype(v) or pd.api.types.is_object_dtype(v))
        and v.map(lambda x: isinstance(x, str)).any()
    )


def _text_arg(v: Value, index: pd.Index) -> pd.Series:
    return _as_series(v, index).astype("string")


def _call(node: Call, data: pd.DataFrame, params: Mapping[str, Any], n: int) -> Value:
    fn = node.fn
    if fn in AGGREGATES:
        raise CalcError(f"{fn} can only be used in an aggregate formula")
    args = [_eval(a, data, params, n) for a in node.args]
    idx = data.index
    with np.errstate(all="ignore"):
        if fn in ("MIN2", "MAX2"):
            a, b = (_as_series(_numeric(x, fn[:3]), idx) for x in args)
            return a.combine(b, min if fn == "MIN2" else max)
        if fn in ("ABS", "FLOOR", "CEILING", "SQRT", "LN", "EXP", "SIGN"):
            x = _numeric(args[0], fn)
            func = {"ABS": np.abs, "FLOOR": np.floor, "CEILING": np.ceil, "SQRT": np.sqrt,
                    "LN": np.log, "EXP": np.exp, "SIGN": np.sign}[fn]  # fmt: skip
            if fn in ("SQRT", "LN"):
                x = _as_series(x, idx)
                x = x.where(x >= 0) if fn == "SQRT" else x.where(x > 0)
            return _clean(func(x))
        if fn == "ROUND":
            digits = int(_numeric(args[1], fn)) if len(args) == 2 else 0
            if not -10 <= digits <= 10:
                raise CalcError("ROUND digits must be between -10 and 10")
            return _as_series(_numeric(args[0], fn), idx).round(digits)
        if fn == "LOG":
            base = _numeric(args[1], fn) if len(args) == 2 else 10.0
            x = _as_series(_numeric(args[0], fn), idx)
            return _clean(np.log(x.where(x > 0)) / np.log(base))
        if fn == "POWER":
            return _clean(np.power(_as_series(_numeric(args[0], fn), idx), _numeric(args[1], fn)))
        if fn == "ZN":
            return _as_series(_numeric(args[0], fn), idx).fillna(0)
        if fn == "IFNULL":
            return _as_series(args[0], idx).where(_as_series(args[0], idx).notna(), args[1])
        if fn == "ISNULL":
            return _as_series(args[0], idx).isna()
        if fn == "FLOAT":
            return _as_series(_numeric(args[0], fn), idx)
        if fn == "INT":
            return np.trunc(_as_series(_numeric(args[0], fn), idx))
        if fn in ("LEN", "UPPER", "LOWER", "TRIM"):
            s = _text_arg(args[0], idx)
            return {
                "LEN": s.str.len,
                "UPPER": s.str.upper,
                "LOWER": s.str.lower,
                "TRIM": s.str.strip,
            }[fn]()
        if fn in ("CONTAINS", "STARTSWITH", "ENDSWITH"):
            s = _text_arg(args[0], idx)
            sub = args[1]
            if not isinstance(sub, str):
                raise CalcError(f"{fn} needs a fixed text to look for")
            if fn == "CONTAINS":
                return s.str.contains(sub, regex=False)
            return s.str.startswith(sub) if fn == "STARTSWITH" else s.str.endswith(sub)
        if fn in ("LEFT", "RIGHT"):
            count = int(_numeric(args[1], fn))
            if not 0 <= count <= 10_000:
                raise CalcError(f"{fn} length must be 0-10000")
            s = _text_arg(args[0], idx)
            return s.str[:count] if fn == "LEFT" else s.str[-count:] if count else s.str[:0]
        if fn in ("YEAR", "QUARTER", "MONTH", "DAY", "WEEKDAY"):
            d = pd.to_datetime(_as_series(args[0], idx), errors="coerce")
            part = {"YEAR": d.dt.year, "QUARTER": d.dt.quarter, "MONTH": d.dt.month, "DAY": d.dt.day,
                    "WEEKDAY": d.dt.day_of_week + 1}[fn]  # fmt: skip
            return part.astype("Int64")
        if fn == "DATEDIFF":
            unit = args[0]
            if unit not in ("day", "week", "month", "quarter", "year"):
                raise CalcError("DATEDIFF unit must be 'day', 'week', 'month', 'quarter' or 'year'")
            a = pd.to_datetime(_as_series(args[1], idx), errors="coerce")
            b = pd.to_datetime(_as_series(args[2], idx), errors="coerce")
            if unit in ("day", "week"):
                days = (b.dt.normalize() - a.dt.normalize()).dt.days
                return days if unit == "day" else np.floor(days / 7)
            months = (b.dt.year - a.dt.year) * 12 + (b.dt.month - a.dt.month)
            return {
                "month": months,
                "quarter": np.floor(months / 3),
                "year": b.dt.year - a.dt.year,
            }[unit]
    raise CalcError(f"unsupported function {fn}")  # pragma: no cover


def evaluate_node(node: Node, data: pd.DataFrame, params: Mapping[str, Any]) -> pd.Series:
    """Evaluate a row-level part of a formula for every row of ``data``."""
    return _as_series(_eval(node, data, params, len(data)), data.index)


def evaluate_aggregate(
    field: CalcField, values: Mapping[Call, pd.Series], params: Mapping[str, Any]
) -> pd.Series:
    """Evaluate an aggregate formula, given the aggregated value of each aggregate call."""
    index = next(iter(values.values())).index if values else pd.RangeIndex(1)

    def ev(node: Node) -> Value:
        if isinstance(node, Call) and node.fn in AGGREGATES:
            return values[node]
        if isinstance(node, Num | Str | Const | ParamRef):
            return _eval(node, pd.DataFrame(index=index), params, len(index))
        frame = pd.DataFrame(index=index)
        if isinstance(node, Unary):
            return _eval(Unary(node.op, _Lit(ev(node.operand))), frame, params, len(index))
        if isinstance(node, Binary):
            lit = Binary(node.op, _Lit(ev(node.left)), _Lit(ev(node.right)))
            return _binary(lit, frame, params, len(index))
        if isinstance(node, Call):
            return _call(
                Call(node.fn, tuple(_Lit(ev(a)) for a in node.args)), frame, params, len(index)
            )
        if isinstance(node, If):
            branches = tuple((_Lit(ev(c)), _Lit(ev(v))) for c, v in node.branches)
            other = _Lit(ev(node.otherwise)) if node.otherwise is not None else None
            return _eval(If(branches, other), frame, params, len(index))
        raise CalcError("unsupported formula element")

    return _as_series(ev(field.tree), index)
