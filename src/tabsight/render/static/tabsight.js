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
      var head = cfg.x_fmt
        ? formatNumber(list[0].axisValue, cfg.x_fmt, locales) // lines over a number
        : list[0].axisValueLabel || list[0].name;
      var rows = ['<div class="ts-tt-head">' + escapeHtml(head) + "</div>"];
      for (var i = 0; i < list.length; i++) {
        var p = list[i];
        var v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
        if (v === null || v === undefined || v === "-") continue;
        if (cfg.skip && cfg.skip.indexOf(p.seriesName) >= 0) continue; // helper series (a forecast band)
        var spec = (cfg.series_fmt && cfg.series_fmt[p.seriesName]) || cfg.fmt;
        var range = "";
        var band = cfg.bands && cfg.bands[p.seriesName];
        if (band && band.low[p.dataIndex] !== null && band.low[p.dataIndex] !== undefined) {
          range = '<span class="ts-tt-share">' + escapeHtml(formatNumber(band.low[p.dataIndex], spec, locales) +
            " – " + formatNumber(band.high[p.dataIndex], spec, locales)) + "</span>";
        }
        rows.push(
          '<div class="ts-tt-row">' + marker(p.color) +
            '<span class="ts-tt-name">' + escapeHtml(p.seriesName) + "</span>" +
            '<span class="ts-tt-value">' + escapeHtml(formatNumber(v, spec, locales)) + "</span>" + range + "</div>"
        );
      }
      return rows.join("");
    };
  }

  // The array behind an item: [x, y, size] for scatter, [min, q1, median, q3, max] for a box.
  function itemArray(p) {
    if (Array.isArray(p.data)) return p.data;
    if (p.data && Array.isArray(p.data.value)) return p.data.value;
    return Array.isArray(p.value) ? p.value : [p.value];
  }

  function itemHead(p, cfg) {
    if (p.data && p.data.source !== undefined && p.data.target !== undefined) {
      return String(p.data.source) + " → " + String(p.data.target); // a Sankey link
    }
    if (cfg.path && Array.isArray(p.treePathInfo) && p.treePathInfo.length > 1) {
      return p.treePathInfo.slice(1).map(function (n) { return n.name; }).join(" › ");
    }
    return p.name !== undefined && p.name !== "" ? p.name : p.seriesName;
  }

  function itemTooltip(cfg, locales) {
    return function (p) {
      if (cfg.fields) {
        // several values for one item, each with its own label and number format
        var arr = itemArray(p);
        var out = '<div class="ts-tt-head">' + escapeHtml(itemHead(p, cfg)) + "</div>";
        cfg.fields.forEach(function (f) {
          var v = arr[f.index];
          if (v === null || v === undefined) return;
          out += '<div class="ts-tt-row"><span class="ts-tt-name">' + escapeHtml(f.label) + "</span>" +
            '<span class="ts-tt-value">' + escapeHtml(formatNumber(v, f.fmt, locales)) + "</span></div>";
        });
        if (p.data && p.data.note) out += '<div class="ts-tt-row ts-tt-note">' + escapeHtml(p.data.note) + "</div>";
        return out;
      }
      var value = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
      if (cfg.no_data && (value === null || value === undefined || value === "-" || value !== value)) {
        // a map region with no row in the data
        return '<div class="ts-tt-head">' + escapeHtml(p.name) + "</div>" +
          '<div class="ts-tt-row"><span class="ts-tt-value">' + escapeHtml(cfg.no_data) + "</span></div>";
      }
      var html =
        '<div class="ts-tt-head">' + escapeHtml(itemHead(p, cfg)) + "</div>" +
        '<div class="ts-tt-row">' + marker(typeof p.color === "string" ? p.color : null) +
        '<span class="ts-tt-value">' + escapeHtml(formatNumber(value, cfg.fmt, locales)) + "</span>";
      if (cfg.percent && typeof p.percent === "number") {
        html += '<span class="ts-tt-share">' + escapeHtml(formatNumber(p.percent, cfg.percent_fmt, locales)) + "</span>";
      }
      html += "</div>";
      if (p.data && p.data.note) html += '<div class="ts-tt-row ts-tt-note">' + escapeHtml(p.data.note) + "</div>";
      return html;
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
      var prefix = typeof node.prefix === "string" ? node.prefix : ""; // "Average " on a reference line
      return function (p) {
        var v = Array.isArray(p.value) ? p.value[p.value.length - 1] : p.value;
        return prefix + formatNumber(v, labelSpec, locales);
      };
    }
    if (node.$tooltip) {
      return node.$tooltip.trigger === "item" ? itemTooltip(node.$tooltip, locales) : axisTooltip(node.$tooltip, locales);
    }
    if (node.$projection) {
      return projection(node.$projection);
    }
    if (node.$render) {
      return RENDERERS[node.$render] || RENDERERS.range;
    }
    var out = {};
    Object.keys(node).forEach(function (key) {
      out[key] = hydrate(node[key], locales);
    });
    return out;
  }

  // ------------------------------------------------------------- custom marks

  // A bar from value[1] to value[2] at category value[0] (waterfall steps can cross zero,
  // which stacked bars can't show honestly). Named, so no code ever travels in the data.
  var RENDERERS = {
    range: function (params, api) {
      var lo = api.coord([api.value(0), api.value(1)]);
      var hi = api.coord([api.value(0), api.value(2)]);
      var width = api.size([1, 0])[0] * 0.62;
      var top = Math.min(lo[1], hi[1]);
      return {
        type: "rect",
        shape: { x: lo[0] - width / 2, y: top, width: width, height: Math.max(1, Math.abs(lo[1] - hi[1])), r: 2 },
        style: api.style(),
      };
    },
  };

  // ------------------------------------------------------------- maps

  // Equal Earth (Šavrič, Patterson and Jenny, 2018): an equal-area world projection.
  var EE = { a1: 1.340264, a2: -0.081106, a3: 0.000893, a4: 0.003796, m: Math.sqrt(3) / 2 };
  var RAD = Math.PI / 180;

  function equalEarth(point) {
    var lambda = point[0] * RAD;
    var theta = Math.asin(EE.m * Math.sin(point[1] * RAD));
    var t2 = theta * theta;
    var t6 = t2 * t2 * t2;
    var x = (lambda * Math.cos(theta)) / (EE.m * (EE.a1 + 3 * EE.a2 * t2 + t6 * (7 * EE.a3 + 9 * EE.a4 * t2)));
    var y = theta * (EE.a1 + EE.a2 * t2 + t6 * (EE.a3 + EE.a4 * t2));
    return [x * 100, -y * 100]; // screen y grows downwards
  }

  function equalEarthInverse(xy) {
    var x = xy[0] / 100;
    var y = -xy[1] / 100;
    var theta = y;
    for (var i = 0; i < 12; i++) {
      var t2 = theta * theta;
      var t6 = t2 * t2 * t2;
      var fy = theta * (EE.a1 + EE.a2 * t2 + t6 * (EE.a3 + EE.a4 * t2)) - y;
      var fpy = EE.a1 + 3 * EE.a2 * t2 + t6 * (7 * EE.a3 + 9 * EE.a4 * t2);
      var step = fy / fpy;
      theta -= step;
      if (Math.abs(step) < 1e-9) break;
    }
    var t2b = theta * theta;
    var t6b = t2b * t2b * t2b;
    var lambda = (EE.m * x * (EE.a1 + 3 * EE.a2 * t2b + t6b * (7 * EE.a3 + 9 * EE.a4 * t2b))) / Math.cos(theta);
    return [lambda / RAD, Math.asin(Math.sin(theta) / EE.m) / RAD];
  }

  function mercator(point) {
    var lat = Math.max(-85, Math.min(85, point[1])) * RAD;
    return [point[0] * RAD * 100, -Math.log(Math.tan(Math.PI / 4 + lat / 2)) * 100];
  }

  function mercatorInverse(xy) {
    return [xy[0] / RAD / 100, (2 * Math.atan(Math.exp(-xy[1] / 100)) - Math.PI / 2) / RAD];
  }

  // Natural Earth (Šavrič et al., 2011), a compromise projection.
  function naturalEarth(point) {
    var lambda = point[0] * RAD;
    var phi = point[1] * RAD;
    var p2 = phi * phi;
    var p4 = p2 * p2;
    var x = lambda * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)));
    var y = phi * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)));
    return [x * 100, -y * 100];
  }

  function naturalEarthInverse(xy) {
    var x = xy[0] / 100;
    var y = -xy[1] / 100;
    var phi = y;
    for (var i = 0; i < 25; i++) {
      var p2 = phi * phi;
      var p4 = p2 * p2;
      var fy = phi * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4))) - y;
      var fpy = 1.007226 + p2 * (0.045255 + p4 * (-0.311325 + 0.259866 * p2 - 0.06507600000000001 * p4));
      var step = fy / fpy;
      phi -= step;
      if (Math.abs(step) < 1e-9) break;
    }
    var q2 = phi * phi;
    var q4 = q2 * q2;
    var lambda = x / (0.8707 - 0.131979 * q2 + q4 * (-0.013791 + q4 * (0.003971 * q2 - 0.001529 * q4)));
    return [lambda / RAD, phi / RAD];
  }

  var PROJECTIONS = {
    equal_earth: [equalEarth, equalEarthInverse],
    mercator: [mercator, mercatorInverse],
    natural: [naturalEarth, naturalEarthInverse],
  };

  function projection(name) {
    var pair = PROJECTIONS[name] || PROJECTIONS.equal_earth;
    return { project: pair[0], unproject: pair[1] };
  }

  // Shapes arrive as TopoJSON (bundled with tabsight, about 80% smaller than GeoJSON).
  // Feature names come from the payload, keyed by feature id.
  function registerMaps(maps) {
    if (!maps || !maps.length) return;
    if (typeof root.topojson === "undefined") throw new Error("tabsight: topojson-client is not loaded");
    maps.forEach(function (m) {
      if (root.echarts.getMap(m.name)) return;
      var collection = root.topojson.feature(m.topo, m.topo.objects[m.object]);
      collection.features.forEach(function (f) {
        f.properties = { name: String((m.names && m.names[f.id]) || f.id) };
      });
      root.echarts.registerMap(m.name, collection);
    });
  }

  // A map keeps its true shape: layoutSize is the largest square side that lets a map of
  // this width/height ratio fit the chart, leaving room for the legend below.
  function fitAspects(option) {
    var geos = Array.isArray(option.geo) ? option.geo : option.geo ? [option.geo] : [];
    return geos.map(function (g) {
      var aspect = g._aspect;
      var box = g._box; // small multiples: [left %, top px, width %, height px]
      delete g._aspect;
      delete g._box;
      return { aspect: typeof aspect === "number" && aspect > 0 ? aspect : null, box: Array.isArray(box) ? box : null };
    });
  }

  function fitSize(a, w, h) {
    return Math.max(40, a >= 1 ? Math.min(w, h * a) : Math.min(h, w / a));
  }

  function fitMaps(chart, aspects) {
    if (!aspects.length) return;
    var width = chart.getWidth();
    var geo = aspects.map(function (f) {
      if (!f || !f.aspect) return {};
      if (f.box) {
        var cw = (width * f.box[2]) / 100 - 12;
        var ch = f.box[3] - 8;
        return {
          layoutCenter: [(width * (f.box[0] + f.box[2] / 2)) / 100, f.box[1] + f.box[3] / 2],
          layoutSize: fitSize(f.aspect, cw, ch),
        };
      }
      var w = width - 16;
      var h = chart.getHeight() - 58;
      return w > 0 && h > 0 ? { layoutSize: fitSize(f.aspect, w, h) } : {};
    });
    chart.setOption({ geo: geo });
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
    registerMaps(figure.maps);
    var chart = root.echarts.init(target, null, { renderer: "canvas" });
    var option = hydrate(figure.option, figure.locales || {});
    var aspects = fitAspects(option);
    chart.setOption(option);
    fitMaps(chart, aspects);
    var refit = function () {
      chart.resize();
      fitMaps(chart, aspects);
    };
    // Watch the chart's own box, not just the window: a notebook can lay a chart out
    // while its cell is off screen (width near zero) and give it its real width later.
    if (typeof root.ResizeObserver === "function") {
      var last = target.clientWidth + "x" + target.clientHeight;
      new root.ResizeObserver(function () {
        var now = target.clientWidth + "x" + target.clientHeight;
        if (now !== last) {
          last = now;
          refit();
        }
      }).observe(target);
    } else if (typeof root.addEventListener === "function") {
      root.addEventListener("resize", refit);
    }
    return chart;
  }

  root.tabsight = {
    version: VERSION,
    render: render,
    formatNumber: formatNumber,
    escapeHtml: escapeHtml,
    hydrate: hydrate,
    registerMaps: registerMaps,
    fitAspects: fitAspects,
    fitMaps: fitMaps,
  };
})(typeof window !== "undefined" ? window : globalThis);
