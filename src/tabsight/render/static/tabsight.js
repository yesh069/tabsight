/*! tabsight runtime | MIT licence | https://github.com/yesh069/tabsight
 *
 * Draws figures produced by the tabsight Python package. Python sends plain JSON:
 * an ECharts option in which number formats appear as {"$fmt": spec} objects, plus
 * the locale data those formats need. This file turns them into functions.
 *
 * Rules: no eval, no network, data is never parsed as HTML (tooltips are escaped strings,
 * tables and KPI cards are built with textContent). Number formatting mirrors
 * tabsight/formats.py exactly; tests/js/parity.cjs checks that they agree.
 */
(function (root) {
  "use strict";

  var VERSION = "0.0.1";
  var NBSP = " ";
  var DURATION_SECONDS = { seconds: 1, minutes: 60, hours: 3600, days: 86400 };

  // ------------------------------------------------------------- decimal rounding

  // Shortest decimal digits of a finite, non-negative number: {digits, exp} where the
  // first digit sits at 10^exp. Same digits as Python's repr().
  function shortestDigits(x) {
    var m = /^(\d)(?:\.(\d+))?e([+-]\d+)$/.exec(x.toExponential());
    return { digits: m[1] + (m[2] || ""), exp: parseInt(m[3], 10) };
  }

  function increment(digits) {
    var chars = digits.split("");
    for (var i = chars.length - 1; i >= 0; i--) {
      if (chars[i] === "9") {
        chars[i] = "0";
      } else {
        chars[i] = String.fromCharCode(chars[i].charCodeAt(0) + 1);
        return chars.join("");
      }
    }
    return "1" + chars.join("");
  }

  // Half-up rounding of |x| to `decimals` places. Returns {whole, frac} digit strings.
  function roundHalfUp(x, decimals) {
    var d = shortestDigits(Math.abs(x));
    var digits = d.digits;
    var point = d.exp + 1; // digits before the decimal point
    if (point <= 0) {
      digits = new Array(1 - point + 1).join("0") + digits;
      point = 1;
    }
    if (digits.length < point) digits += new Array(point - digits.length + 1).join("0");
    var keep = point + decimals;
    if (digits.length > keep) {
      var up = digits.charCodeAt(keep) >= 53; // first dropped digit >= "5"
      digits = digits.slice(0, keep);
      if (up) {
        var bigger = increment(digits);
        if (bigger.length > digits.length) point += 1;
        digits = bigger;
      }
    } else {
      digits += new Array(keep - digits.length + 1).join("0");
    }
    var whole = digits.slice(0, point).replace(/^0+(?=\d)/, "");
    return { whole: whole || "0", frac: digits.slice(point) };
  }

  function roundedValue(x, decimals) {
    var r = roundHalfUp(x, decimals);
    return parseFloat(r.whole + (r.frac ? "." + r.frac : ""));
  }

  // ------------------------------------------------------------- number formatting

  function group(digits, loc) {
    if (digits.length <= 3 || !loc.group) return digits;
    var first = loc.grouping[0];
    var size = loc.grouping.length > 1 ? loc.grouping[1] : first;
    var head = digits.slice(0, digits.length - first);
    var parts = [digits.slice(digits.length - first)];
    while (head) {
      parts.push(head.slice(Math.max(0, head.length - size)));
      head = head.slice(0, Math.max(0, head.length - size));
    }
    return parts.reverse().join(loc.group);
  }

  function fixed(value, decimals, loc, grouped, strip) {
    var r = roundHalfUp(value, decimals);
    var frac = strip ? r.frac.replace(/0+$/, "") : r.frac;
    var whole = grouped === false ? r.whole : group(r.whole, loc);
    return whole + (frac ? loc.decimal + frac : "");
  }

  function compact(value, loc, decimals) {
    if (decimals === undefined) decimals = 1;
    var v = Math.abs(value);
    var sep = loc.compact_space ? NBSP : "";
    for (var i = 0; i < loc.compact.length; i++) {
      var threshold = loc.compact[i][0];
      var suffix = loc.compact[i][1];
      if (v >= threshold) {
        if (i > 0) {
          var limit = Math.trunc(loc.compact[i - 1][0] / threshold);
          if (roundedValue(v / threshold, decimals) >= limit) {
            var bigger = loc.compact[i - 1][0];
            return fixed(v / bigger, decimals, loc, true, true) + sep + loc.compact[i - 1][1];
          }
        }
        return fixed(v / threshold, decimals, loc, true, true) + sep + suffix;
      }
    }
    if (v === Math.trunc(v)) return fixed(v, 0, loc);
    return fixed(v, v < 10 ? 2 : 1, loc, true, true);
  }

  function signed(body, number, negative, sign) {
    if (number < 0 && /[1-9]/.test(body)) {
      return negative === "parens" ? "(" + body + ")" : "-" + body;
    }
    if (sign && number > 0) return "+" + body;
    return body;
  }

  function duration(value, unit, loc) {
    var seconds = value * DURATION_SECONDS[unit];
    if (!isFinite(seconds)) return null;
    if (seconds >= 2 * 86400) return fixed(seconds / 86400, 1, loc, true, true) + " days";
    var whole = parseInt(roundHalfUp(seconds, 0).whole, 10);
    if (seconds >= 3600) return Math.floor(whole / 3600) + "h " + Math.floor((whole % 3600) / 60) + "m";
    if (seconds >= 60) return Math.floor(whole / 60) + "m " + (whole % 60) + "s";
    return fixed(seconds, seconds >= 10 ? 0 : 1, loc, true, true) + "s";
  }

  function formatNumber(value, spec, locales) {
    if (value === null || value === undefined || value === "") return "";
    var number = typeof value === "number" ? value : parseFloat(value);
    if (!isFinite(number)) return "";
    var loc = locales[spec.locale];
    if (!loc) throw new Error("tabsight: no locale data for " + spec.locale);
    var unit = spec.unit;
    var decimals = spec.decimals;
    var hasDecimals = decimals !== null && decimals !== undefined;

    if (spec.pattern) {
      var p = spec.pattern;
      var shown = Math.abs(number) * (p.percent ? 100 : 1);
      if (!isFinite(shown)) return "";
      var body = p.prefix + fixed(shown, p.decimals, loc, p.grouped) + p.suffix;
      return signed(body, number, spec.negative, spec.sign);
    }
    if (unit === "percent" || unit === "pp") {
      var pct = spec.percent_scale === "fraction" ? number * 100 : number;
      if (!isFinite(pct)) return "";
      var text = fixed(pct, hasDecimals ? decimals : 1, loc, true, !hasDecimals);
      var suffix = unit === "pp" ? " pp" : (loc.percent_space ? NBSP : "") + "%";
      return signed(text + suffix, pct, spec.negative, spec.sign || unit === "pp");
    }
    if (unit === "duration") {
      var dur = duration(Math.abs(number), spec.duration_unit, loc);
      return dur === null ? "" : signed(dur, number, spec.negative, spec.sign);
    }
    if (unit === "currency") {
      var amount;
      if (spec.style === "compact") {
        amount = compact(number, loc);
      } else {
        var d = hasDecimals ? decimals : spec.zero_decimal || Math.abs(number) >= 1000 ? 0 : 2;
        amount = fixed(number, d, loc);
      }
      var space = loc.currency_space ? NBSP : "";
      var symbol = spec.currency_symbol;
      amount = loc.currency_before ? symbol + space + amount : amount + space + symbol.trim();
      return signed(amount, number, spec.negative, spec.sign);
    }
    if (spec.style === "compact") return signed(compact(number, loc), number, spec.negative, spec.sign);
    if (unit === "count") {
      return signed(fixed(number, hasDecimals ? decimals : 0, loc), number, spec.negative, spec.sign);
    }
    var places = hasDecimals ? decimals : number === Math.trunc(number) ? 0 : 2;
    return signed(fixed(number, places, loc, true, !hasDecimals && places > 0), number, spec.negative, spec.sign);
  }

  // ------------------------------------------------------------- safety helpers

  var ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (c) {
      return ESCAPES[c];
    });
  }

  // ECharts builds tooltip markers from series colours. Colours are validated hex codes
  // in Python; this re-checks before anything reaches HTML.
  function safeColor(color) {
    return typeof color === "string" && /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : "#999999";
  }

  function marker(color) {
    return (
      '<span style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;background:' +
      safeColor(color) +
      '"></span>'
    );
  }

  // ------------------------------------------------------------- hydration

  function axisTooltip(cfg, locales) {
    return function (params) {
      var list = Array.isArray(params) ? params : [params];
      if (!list.length) return "";
      var rows = ['<div class="ts-tt-head">' + escapeHtml(list[0].axisValueLabel || list[0].name) + "</div>"];
      for (var i = 0; i < list.length; i++) {
        var p = list[i];
        if (p.value === null || p.value === undefined || p.value === "-") continue;
        var spec = (cfg.series_fmt && cfg.series_fmt[p.seriesName]) || cfg.fmt;
        rows.push(
          '<div class="ts-tt-row">' + marker(p.color) +
            '<span class="ts-tt-name">' + escapeHtml(p.seriesName) + "</span>" +
            '<span class="ts-tt-value">' + escapeHtml(formatNumber(p.value, spec, locales)) + "</span></div>"
        );
      }
      return rows.join("");
    };
  }

  function itemTooltip(cfg, locales) {
    return function (p) {
      var value = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
      var html =
        '<div class="ts-tt-head">' + escapeHtml(p.name) + "</div>" +
        '<div class="ts-tt-row">' + marker(p.color) +
        '<span class="ts-tt-value">' + escapeHtml(formatNumber(value, cfg.fmt, locales)) + "</span>";
      if (cfg.percent && typeof p.percent === "number") {
        html += '<span class="ts-tt-share">' + escapeHtml(formatNumber(p.percent, cfg.percent_fmt, locales)) + "</span>";
      }
      return html + "</div>";
    };
  }

  // Replace {"$fmt": spec}, {"$label": spec} and {"$tooltip": cfg} with functions.
  function hydrate(node, locales) {
    if (Array.isArray(node)) {
      return node.map(function (item) {
        return hydrate(item, locales);
      });
    }
    if (node === null || typeof node !== "object") return node;
    if (node.$fmt) {
      var spec = node.$fmt;
      return function (value) {
        return formatNumber(value, spec, locales);
      };
    }
    if (node.$label) {
      var labelSpec = node.$label;
      return function (p) {
        var v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
        return formatNumber(v, labelSpec, locales);
      };
    }
    if (node.$tooltip) {
      return node.$tooltip.trigger === "item" ? itemTooltip(node.$tooltip, locales) : axisTooltip(node.$tooltip, locales);
    }
    var out = {};
    Object.keys(node).forEach(function (key) {
      out[key] = hydrate(node[key], locales);
    });
    return out;
  }

  // ------------------------------------------------------------- non-ECharts figures

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function renderKpi(target, kpi) {
    var card = el("div", "ts-kpi");
    card.appendChild(el("div", "ts-kpi__value", kpi.value_text));
    if (kpi.label) card.appendChild(el("div", "ts-kpi__label", kpi.label));
    if (kpi.detail) card.appendChild(el("div", "ts-kpi__detail", kpi.detail));
    if (kpi.value_full) card.title = kpi.value_full;
    target.appendChild(card);
  }

  function renderTable(target, table) {
    var wrap = el("div", "ts-table-wrap");
    var t = el("table", "ts-table");
    var thead = el("thead");
    var hr = el("tr");
    table.columns.forEach(function (c) {
      var th = el("th", "ts-align-" + (c.align === "right" ? "right" : "left"), c.name);
      th.scope = "col";
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    t.appendChild(thead);
    var tbody = el("tbody");
    table.rows.forEach(function (row) {
      var tr = el("tr");
      row.forEach(function (cell, i) {
        var align = table.columns[i].align === "right" ? "right" : "left";
        tr.appendChild(el("td", "ts-align-" + align, cell));
      });
      tbody.appendChild(tr);
    });
    t.appendChild(tbody);
    wrap.appendChild(t);
    target.appendChild(wrap);
    if (table.note) target.appendChild(el("p", "ts-note", table.note));
  }

  // ------------------------------------------------------------- entry point

  function render(target, figure) {
    if (!target || !figure) throw new Error("tabsight.render needs a target element and a figure");
    target.textContent = "";
    if (figure.kind === "kpi") return renderKpi(target, figure.kpi);
    if (figure.kind === "table") return renderTable(target, figure.table);
    if (typeof root.echarts === "undefined") throw new Error("tabsight: ECharts is not loaded");
    var chart = root.echarts.init(target, null, { renderer: "canvas" });
    chart.setOption(hydrate(figure.option, figure.locales || {}));
    if (typeof root.addEventListener === "function") {
      root.addEventListener("resize", function () {
        chart.resize();
      });
    }
    return chart;
  }

  root.tabsight = {
    version: VERSION,
    render: render,
    formatNumber: formatNumber,
    escapeHtml: escapeHtml,
    hydrate: hydrate,
  };
})(typeof window !== "undefined" ? window : globalThis);
