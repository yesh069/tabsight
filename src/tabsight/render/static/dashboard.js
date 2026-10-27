/*
 * tabsight dashboard runtime: filters, cross-filtering and exact re-aggregation.
 *
 * The page holds one shared, pre-aggregated table (never raw rows). When the viewer
 * filters, this file keeps the matching rows, adds up their parts again with the same
 * rules as tabsight/aggregate.py (sums and counts for averages, minimums and maximums),
 * and puts the new numbers into each tile's chart. Python and this file are checked
 * against each other by tests/js/dashboard_parity.cjs.
 *
 * Rules: no eval, no network, no HTML from data (every text goes through textContent or
 * tabsight.escapeHtml), and values read from the address bar are matched against the
 * table's known values before use.
 */
(function (root) {
  "use strict";

  var OTHER_KEY = "\u0000other";
  var HELPER = "​";
  var MAX_TABLE_ROWS = 500;
  var LABELS_UP_TO = 8;
  var MARKERS_BELOW = 30;

  // ------------------------------------------------------------- small helpers

  function clone(v) {
    return v === undefined ? v : JSON.parse(JSON.stringify(v));
  }

  function naturalParts(v) {
    var s = String(v).slice(0, 200).toLowerCase();
    var parts = s.split(/(\d+)/);
    return parts.map(function (p, i) {
      return i % 2 ? parseInt(p, 10) : p;
    });
  }

  // Same order as Python's natural_key: 'Item 2' before 'Item 10'.
  function naturalCompare(a, b) {
    var pa = naturalParts(a);
    var pb = naturalParts(b);
    for (var i = 0; i < Math.min(pa.length, pb.length); i++) {
      if (pa[i] < pb[i]) return -1;
      if (pa[i] > pb[i]) return 1;
    }
    return pa.length - pb.length;
  }

  // Compensated (Kahan) sums, so totals match Python to the last digits.
  function Acc() {
    this.sum = 0;
    this.c = 0;
    this.any = false;
  }
  Acc.prototype.add = function (v) {
    var y = v - this.c;
    var t = this.sum + y;
    this.c = t - this.sum - y;
    this.sum = t;
    this.any = true;
  };

  // ------------------------------------------------------------- the shared table

  function Table(data) {
    this.n = data.rows;
    this.dims = data.dims;
    this.nums = data.nums;
    this.labels = data.labels || {};
    this.meta = data.meta || {};
  }
  Table.prototype.key = function (col, r) {
    var d = this.dims[col];
    return d.values[d.codes[r]];
  };
  Table.prototype.known = function (col) {
    return this.dims[col] ? this.dims[col].values : [];
  };

  // Rows that pass the filters. `skip` is a tile id: filters that tile made itself are
  // not applied to it (the source tile highlights instead of filtering itself).
  function matching(table, filters, skip, ignoreCol) {
    var active = [];
    for (var col in filters) {
      if (!Object.prototype.hasOwnProperty.call(filters, col)) continue;
      var f = filters[col];
      if (f.mode === "highlight" || col === ignoreCol) continue;
      if (skip && f.source === skip) continue;
      active.push([col, f]);
    }
    var out = [];
    for (var r = 0; r < table.n; r++) {
      var ok = true;
      for (var i = 0; i < active.length && ok; i++) {
        var key = table.key(active[i][0], r);
        var g = active[i][1];
        if (g.type === "range") ok = key !== null && key >= g.lo && key <= g.hi;
        else ok = g.set.hasOwnProperty(key === null ? "\u0000null" : key);
      }
      if (ok) out.push(r);
    }
    return out;
  }

  function newParts() {
    return { rows: 0, acc: {}, min: {}, max: {} };
  }

  function addRow(table, parts, r, measures) {
    parts.rows += table.nums.__rows[r] || 0;
    measures.forEach(function (m) {
      for (var p in m.parts) {
        var col = m.parts[p];
        var v = table.nums[col][r];
        if (v === null || v === undefined) continue;
        if (p === "min") parts.min[col] = col in parts.min ? Math.min(parts.min[col], v) : v;
        else if (p === "max") parts.max[col] = col in parts.max ? Math.max(parts.max[col], v) : v;
        else {
          if (!parts.acc[col]) parts.acc[col] = new Acc();
          parts.acc[col].add(v);
        }
      }
    });
  }

  function merge(into, from) {
    into.rows += from.rows;
    var k;
    for (k in from.acc) {
      if (!into.acc[k]) into.acc[k] = new Acc();
      into.acc[k].add(from.acc[k].sum);
    }
    for (k in from.min) into.min[k] = k in into.min ? Math.min(into.min[k], from.min[k]) : from.min[k];
    for (k in from.max) into.max[k] = k in into.max ? Math.max(into.max[k], from.max[k]) : from.max[k];
  }

  // The measure's value from its parts, as tabsight/aggregate.py _finish does.
  function finish(parts, m, minGroup) {
    if (minGroup && parts.rows < minGroup) return null;
    var P = m.parts;
    var get = function (name) {
      var a = parts.acc[P[name]];
      return a && a.any ? a.sum : null;
    };
    if (P.count === "__rows") return parts.rows;
    if (m.agg === "sum") return get("sum");
    if (m.agg === "count") return get("count") || 0;
    if (m.agg === "mean") {
      var c = get("count");
      return c ? get("sum") / c : null;
    }
    if (m.agg === "min") return P.min in parts.min ? parts.min[P.min] : null;
    if (m.agg === "max") return P.max in parts.max ? parts.max[P.max] : null;
    return null;
  }

  // Group the given rows by `dims`: {id -> {keys, parts}} plus the ids in first-seen order.
  function group(table, rows, dims, measures) {
    var groups = {};
    var order = [];
    rows.forEach(function (r) {
      var keys = dims.map(function (d) {
        return table.key(d, r);
      });
      var id = JSON.stringify(keys);
      var g = groups[id];
      if (!g) {
        g = groups[id] = { keys: keys, parts: newParts() };
        order.push(id);
      }
      addRow(table, g.parts, r, measures);
    });
    return { groups: groups, order: order };
  }

  // ------------------------------------------------------------- models

  function zeroWhenEmpty(m) {
    return m.agg === "sum" || m.agg === "count";
  }

  // Bars, lines, areas and donuts: one category axis, maybe one series per colour value.
  function categoryModel(table, b, rows, ctx) {
    var measures = b.measures;
    var xcol = b.dims[0];
    var ccol = b.dims[1] || null;
    var byX = group(table, rows, [xcol], measures);
    var xs = byX.order.map(function (id) {
      return byX.groups[id].keys[0];
    });
    var other = [];
    if (b.top && !b.time) {
      // Rank by the first measure at the category level (exactly like aggregate._top_n).
      var ranked = xs.slice().sort(function (a, c) {
        var va = finish(byX.groups[JSON.stringify([a])].parts, measures[0], null);
        var vc = finish(byX.groups[JSON.stringify([c])].parts, measures[0], null);
        if (va === null && vc !== null) return 1;
        if (vc === null && va !== null) return -1;
        if (va !== vc) return vc - va;
        return naturalCompare(a, c);
      });
      if (ranked.length > b.top + 1) {
        var keep = {};
        ranked.slice(0, b.top).forEach(function (k) {
          keep[k === null ? "\u0000null" : k] = 1;
        });
        other = ranked.slice(b.top).sort(naturalCompare);
        xs = ranked.slice(0, b.top).concat([OTHER_KEY]);
        ctx.otherSet = {};
        other.forEach(function (k) {
          ctx.otherSet[k === null ? "\u0000null" : k] = 1;
        });
        ctx.keep = keep;
      }
    }
    var inOther = function (k) {
      return ctx.otherSet && ctx.otherSet.hasOwnProperty(k === null ? "\u0000null" : k);
    };
    // Cells: (x, colour) -> parts, with the Other members merged into one x.
    var cells = {};
    var colours = [];
    var seenColour = {};
    rows.forEach(function (r) {
      var xk = table.key(xcol, r);
      if (inOther(xk)) xk = OTHER_KEY;
      var ck = ccol ? table.key(ccol, r) : null;
      var id = JSON.stringify([xk, ck]);
      if (!cells[id]) cells[id] = newParts();
      addRow(table, cells[id], r, measures);
      if (ccol) {
        var cid = ck === null ? "\u0000null" : ck;
        if (!seenColour[cid]) {
          seenColour[cid] = 1;
          colours.push(ck);
        }
      }
    });
    var value = function (xk, ck, m) {
      var p = cells[JSON.stringify([xk, ck])];
      return p ? finish(p, m, ctx.minGroup) : undefined;
    };
    // Order of the categories (aggregate._sort).
    if (b.time) {
      xs = xs.slice().sort();
      if (b.periods && b.missing !== "connect" && xs.length) {
        var lo = b.periods.indexOf(xs[0]);
        var hi = b.periods.indexOf(xs[xs.length - 1]);
        if (lo >= 0 && hi >= lo) xs = b.periods.slice(lo, hi + 1);
      }
    } else if (b.sort === "order" && b.order) {
      var pos = {};
      b.order.forEach(function (k, i) {
        pos[k] = i;
      });
      xs.sort(function (a, c) {
        var pa = a in pos ? pos[a] : b.order.length;
        var pc = c in pos ? pos[c] : b.order.length;
        return pa - pc || naturalCompare(a, c);
      });
    } else if (b.sort === "natural") {
      xs.sort(naturalCompare);
    } else {
      var total = {};
      xs.forEach(function (xk) {
        var t = 0;
        var any = false;
        (ccol ? colours : [null]).forEach(function (ck) {
          var v = value(xk, ck, measures[0]);
          if (v !== null && v !== undefined) {
            t += v;
            any = true;
          }
        });
        total[xk] = any ? t : 0;
      });
      var asc = b.sort === "asc";
      xs.sort(function (a, c) {
        var oa = a === OTHER_KEY ? 1 : 0;
        var oc = c === OTHER_KEY ? 1 : 0;
        if (oa !== oc) return oa - oc;
        if (total[a] !== total[c]) return asc ? total[a] - total[c] : total[c] - total[a];
        return naturalCompare(a, c);
      });
    }
    if (!b.time) {
      // Other always goes last
      var o = xs.indexOf(OTHER_KEY);
      if (o >= 0) xs = xs.slice(0, o).concat(xs.slice(o + 1), [OTHER_KEY]);
    }
    var fill = function (m) {
      if (!b.time || b.missing === "connect") return null;
      return b.missing === "zero" && zeroWhenEmpty(m) ? 0 : null;
    };
    var series = [];
    if (!ccol) {
      measures.forEach(function (m) {
        series.push({
          key: m.label,
          name: m.label,
          values: xs.map(function (xk) {
            var v = value(xk, null, m);
            return v === undefined ? fill(m) : v;
          }),
        });
      });
    } else {
      var names = colours.filter(function (c) {
        return c !== null;
      });
      names.sort(naturalCompare);
      if (colours.indexOf(null) >= 0) names.push(null);
      names.forEach(function (ck) {
        series.push({
          key: ck,
          name: ck === null ? ctx.unknown : String(ck),
          values: xs.map(function (xk) {
            var v = value(xk, ck, measures[0]);
            return v === undefined ? fill(measures[0]) : v;
          }),
        });
      });
    }
    return { keys: xs, other: other, series: series };
  }

  function categoryLabels(table, b, keys, ctx) {
    var labels = table.labels[b.dims[0]];
    var style = labels && keys.length > 8 && /\|(month|day)$/.test(b.dims[0]) ? "compact" : "full";
    return keys.map(function (k) {
      if (k === OTHER_KEY) return ctx.other + " (" + ctx.otherCount + ")";
      if (k === null) return ctx.unknown;
      if (labels) return labels[style][k] || k;
      return String(k);
    });
  }

  // ------------------------------------------------------------- rebuilding options

  function isHelper(s) {
    var name = String(s.name || "");
    return name.charAt(0) === HELPER || (s.lineStyle && s.lineStyle.type === "dashed");
  }

  function selectedSet(sel) {
    return sel ? sel.set : null;
  }

  function dimmed(set, key) {
    return set && !set.hasOwnProperty(key === null ? "\u0000null" : key);
  }

  function cartesian(fig, b, model, labels, payload, sel) {
    var opt = clone(fig.option);
    var cat = b.horizontal ? opt.yAxis : opt.xAxis;
    cat.data = labels;
    var real = opt.series.filter(function (s) {
      return (s.type === "bar" || s.type === "line") && !isHelper(s);
    });
    var tmpl = real[0];
    var set = selectedSet(sel);
    var stacked100 = fig.kind === "stacked100_bar";
    var totals = null;
    if (stacked100) {
      totals = model.keys.map(function (_, i) {
        var t = 0;
        model.series.forEach(function (s) {
          if (s.values[i] !== null) t += Math.abs(s.values[i]);
        });
        return t;
      });
    }
    var fmt = opt.tooltip && opt.tooltip.formatter && opt.tooltip.formatter.$tooltip;
    var anyFmt = fmt && fmt.series_fmt ? fmt.series_fmt[Object.keys(fmt.series_fmt)[0]] : null;
    var seriesFmt = {};
    var out = model.series.map(function (s, j) {
      var base = b.dims.length > 1 ? clone(tmpl) : clone(real[j] || tmpl);
      base.name = s.name;
      var color = null;
      if (b.dims.length > 1) {
        color = payload.colors[s.name] || (base.itemStyle && base.itemStyle.color);
        base.itemStyle = base.itemStyle || {};
        base.itemStyle.color = color;
        if (base.lineStyle) base.lineStyle.color = color;
        if (base.areaStyle) base.areaStyle.color = color;
      }
      base.data = s.values.map(function (v, i) {
        if (stacked100) v = v !== null && totals[i] ? v / totals[i] : null;
        var key = model.keys[i];
        var item = v;
        if (base.type === "bar" && b.dims.length === 1 && model.series.length === 1 && key === OTHER_KEY) {
          item = { value: v, itemStyle: { color: payload.other_color } };
        }
        if (set && dimmed(set, key) && key !== OTHER_KEY) {
          item = { value: v, itemStyle: { opacity: 0.25 } };
        }
        return item;
      });
      if (base.type === "line") base.showSymbol = model.keys.length < MARKERS_BELOW;
      if (base.type === "bar" && model.series.length === 1 && b.dims.length === 1) {
        if (model.keys.length <= LABELS_UP_TO) {
          base.label = {
            show: true,
            position: b.horizontal ? "right" : "top",
            color: payload.theme.text_secondary,
            fontSize: 11,
            formatter: { $label: b.measures[0].compact },
          };
        } else {
          delete base.label;
        }
      }
      delete base.markLine;
      delete base.markArea;
      delete base.markPoint;
      seriesFmt[s.name] = stacked100 ? anyFmt : (b.measures[j] || b.measures[0]).full;
      return base;
    });
    opt.series = out;
    if (fmt) fmt.series_fmt = seriesFmt;
    if (fmt && fmt.bands) {
      delete fmt.bands;
      delete fmt.skip;
    }
    if (opt.legend && opt.legend.data) delete opt.legend.data;
    if (opt.legend && out.length < 2 && b.dims.length < 2) delete opt.legend;
    if (opt.legend && opt.legend.selected) delete opt.legend.selected;
    return opt;
  }

  function donut(fig, b, model, labels, payload, sel) {
    var opt = clone(fig.option);
    var set = selectedSet(sel);
    var values = model.series[0].values;
    opt.series[0].data = model.keys.map(function (k, i) {
      var item = {
        name: labels[i],
        value: values[i],
        itemStyle: { color: k === OTHER_KEY ? payload.other_color : payload.colors[labels[i]] || payload.other_color },
      };
      if (set && dimmed(set, k) && k !== OTHER_KEY) item.itemStyle.opacity = 0.3;
      return item;
    });
    return opt;
  }

  function geo(fig, b, table, rows, ctx, sel) {
    var opt = clone(fig.option);
    var m = b.measures[0];
    var byShape = {};
    var order = [];
    var g = group(table, rows, b.dims, b.measures);
    g.order.forEach(function (id) {
      var k = g.groups[id].keys[0];
      var shape = k === null ? null : b.shapes[k];
      if (!shape) return;
      if (!byShape[shape]) {
        byShape[shape] = newParts();
        order.push(shape);
      }
      merge(byShape[shape], g.groups[id].parts);
    });
    var set = selectedSet(sel);
    var selectedShapes = {};
    if (set) {
      for (var raw in b.shapes) if (!dimmed(set, raw)) selectedShapes[b.shapes[raw]] = 1;
    }
    var nums = [];
    opt.series[0].data = order.map(function (shape) {
      var v = finish(byShape[shape], m, ctx.minGroup);
      if (v !== null) nums.push(v);
      return { name: shape, value: v };
    });
    if (set) {
      // A map drawn on a shared geo takes its region styles from the geo, not the data.
      var geoOpt = Array.isArray(opt.geo) ? opt.geo[0] : opt.geo;
      if (geoOpt) {
        geoOpt.regions = order
          .filter(function (shape) {
            return !selectedShapes[shape];
          })
          .map(function (shape) {
            return { name: shape, itemStyle: { opacity: 0.3 } };
          });
      }
    }
    opt.series = opt.series.slice(0, 1); // tiny-country dots are drawn from all the data only
    var lo = nums.length ? Math.min.apply(null, nums) : 0;
    var hi = nums.length ? Math.max.apply(null, nums) : 1;
    if (lo < 0 && hi > 0) {
      var bound = Math.max(-lo, hi);
      lo = -bound;
      hi = bound;
    }
    if (hi === lo) hi = lo + (Math.abs(lo) || 1);
    var vm = opt.visualMap;
    if (vm) {
      vm.min = lo;
      vm.max = hi;
      var tsj = root.tabsight;
      vm.text = [tsj.formatNumber(hi, m.compact, ctx.locales), tsj.formatNumber(lo, m.compact, ctx.locales)];
    }
    return opt;
  }

  function kpi(fig, b, table, filters, tileId, ctx) {
    var tsj = root.tabsight;
    var m = b.measures[0];
    var out = clone(fig.kpi);
    var c = b.compare;
    var cur;
    var prev;
    var curLabel;
    var prevLabel;
    if (!c) {
      cur = total(table, matching(table, filters, tileId), b.measures, ctx);
      out.value_text = cur === null ? ctx.words.no_data : tsj.formatNumber(cur, m.compact, ctx.locales);
      out.value_full = cur === null ? "" : tsj.formatNumber(cur, m.full, ctx.locales);
      return out;
    }
    var range = filters[c.month];
    if (range && range.type === "range") {
      // A date filter sets the window; the same window shifted back is the comparison.
      cur = total(table, matching(table, filters, tileId), b.measures, ctx);
      var shifted = { type: "range", lo: shiftMonth(range.lo, -c.shift), hi: shiftMonth(range.hi, -c.shift) };
      var prevFilters = {};
      for (var k in filters) prevFilters[k] = filters[k];
      prevFilters[c.month] = shifted;
      prev = total(table, matching(table, prevFilters, tileId), b.measures, ctx);
      curLabel = monthSpan(table, c.month, range.lo, range.hi);
      prevLabel = monthSpan(table, c.month, shifted.lo, shifted.hi);
    } else {
      var only = function (which) {
        var f = {};
        for (var k2 in filters) f[k2] = filters[k2];
        var set = {};
        set[which] = 1;
        f[c.window] = { type: "in", set: set, mode: "filter" };
        return total(table, matching(table, f, tileId), b.measures, ctx);
      };
      cur = only("cur");
      prev = only("prev");
      curLabel = c.current_label;
      prevLabel = c.previous_label;
    }
    var change;
    var word = { previous_year: "year", previous_quarter: "quarter", previous_month: "month" }[c.how];
    if (prev === null) change = "no data for the previous " + word;
    else if (cur === null) change = "no data for the current " + word;
    else {
      var d = cur - prev;
      var arrow = d > 0 ? "▲" : d < 0 ? "▼" : "■";
      var size;
      if (c.pp) size = tsj.formatNumber(Math.abs(d), c.pp_fmt, ctx.locales).replace(/^\+/, "");
      else if (prev !== 0) size = tsj.formatNumber(Math.abs(d / Math.abs(prev)), c.pct_fmt, ctx.locales);
      else size = tsj.formatNumber(Math.abs(d), m.compact, ctx.locales);
      change = arrow + " " + size + " vs " + prevLabel;
    }
    out.value_text = cur === null ? ctx.words.no_data : tsj.formatNumber(cur, m.compact, ctx.locales);
    out.value_full = cur === null ? "" : tsj.formatNumber(cur, m.full, ctx.locales) + " in " + curLabel;
    out.detail = curLabel + " · " + change;
    return out;
  }

  function total(table, rows, measures, ctx) {
    var parts = newParts();
    rows.forEach(function (r) {
      addRow(table, parts, r, measures);
    });
    return rows.length ? finish(parts, measures[0], ctx.minGroup) : null;
  }

  function shiftMonth(key, months) {
    var y = parseInt(key.slice(0, 4), 10);
    var mo = parseInt(key.slice(5, 7), 10) - 1 + months;
    y += Math.floor(mo / 12);
    mo = ((mo % 12) + 12) % 12;
    return String(y) + "-" + (mo < 9 ? "0" : "") + String(mo + 1) + key.slice(7);
  }

  function monthSpan(table, col, lo, hi) {
    var labels = (table.labels[col] || {}).full || {};
    var a = labels[lo] || lo.slice(0, 7);
    var z = labels[hi] || hi.slice(0, 7);
    return a === z ? a : a + " – " + z;
  }

  function tableModel(fig, b, table, rows, ctx) {
    var out = clone(fig.table);
    var g = group(table, rows, b.dims, b.measures);
    var list = g.order.map(function (id) {
      var grp = g.groups[id];
      return {
        keys: grp.keys,
        values: b.measures.map(function (m) {
          return finish(grp.parts, m, ctx.minGroup);
        }),
      };
    });
    var first = b.dims[0];
    var firstTotals = {};
    list.forEach(function (row) {
      var k = JSON.stringify(row.keys[0]);
      var v = row.values[0];
      firstTotals[k] = (firstTotals[k] || 0) + (v === null || v === undefined ? 0 : v);
    });
    var pos = {};
    (b.order || []).forEach(function (k, i) {
      pos[k] = i;
    });
    list.sort(function (a, c) {
      var ka = a.keys[0];
      var kc = c.keys[0];
      var d = 0;
      if (b.sort === "time") d = ka < kc ? -1 : ka > kc ? 1 : 0;
      else if (b.sort === "order") d = (ka in pos ? pos[ka] : 1e9) - (kc in pos ? pos[kc] : 1e9);
      else if (b.sort === "natural") d = 0;
      else {
        var ta = firstTotals[JSON.stringify(ka)];
        var tc = firstTotals[JSON.stringify(kc)];
        d = b.sort === "asc" ? ta - tc : tc - ta;
      }
      if (d) return d;
      d = naturalCompare(ka, kc);
      if (d) return d;
      for (var i = 1; i < a.keys.length; i++) {
        var x = a.keys[i];
        var y = c.keys[i];
        var timeDim = /\|[a-z]+$/.test(b.dims[i]);
        d = timeDim ? (x < y ? -1 : x > y ? 1 : 0) : naturalCompare(x, y);
        if (d) return d;
      }
      return 0;
    });
    var shown = list.slice(0, MAX_TABLE_ROWS);
    var tsj = root.tabsight;
    out.rows = shown.map(function (row, i) {
      var cells = row.keys.map(function (k, level) {
        var labels = table.labels[b.dims[level]];
        var label = k === null ? ctx.unknown : labels ? labels.full[k] || k : String(k);
        var repeated = level < row.keys.length - 1 && i > 0;
        if (repeated) {
          for (var p = 0; p <= level; p++) {
            if (shown[i - 1].keys[p] !== row.keys[p]) repeated = false;
          }
        }
        return repeated ? "" : label;
      });
      row.values.forEach(function (v, j) {
        cells.push(tsj.formatNumber(v, b.formats[j] || b.measures[j].full, ctx.locales));
      });
      return cells;
    });
    out.note = list.length > MAX_TABLE_ROWS ? "showing the first 500 of " + list.length + " rows" : null;
    void first;
    return { table: out, keys: shown.map(function (row) { return row.keys[0]; }), rows: list };
  }

  // ------------------------------------------------------------- one tile, given filters

  // Recompute a tile: returns {figure, keys, other} (pure; used by the page and the tests).
  function compute(payload, table, tile, filters) {
    var b = tile.binding;
    var fig = clone(tile.figure);
    var ctx = {
      unknown: payload.unknown,
      other: payload.other,
      minGroup: payload.min_group_size,
      locales: payload.locales,
      words: payload.words,
    };
    var sel = tile.action === "filter" && b.click ? filters[b.click] : null;
    if (sel && sel.source !== tile.id) sel = null;
    var hl = b.click && filters[b.click] && filters[b.click].mode === "highlight" ? filters[b.click] : null;
    var rows = matching(table, filters, tile.action === "filter" ? tile.id : null);
    if (b.shape === "value") {
      fig.kpi = kpi(fig, b, table, filters, tile.action === "filter" ? tile.id : null, ctx);
      return { figure: fig, keys: [] };
    }
    if (b.shape === "geo") {
      fig.option = geo(fig, b, table, rows, ctx, sel || hl);
      return { figure: fig, keys: [] };
    }
    if (b.shape === "rows") {
      var t = tableModel(fig, b, table, rows, ctx);
      fig.table = t.table;
      return { figure: fig, keys: t.keys, rows: t.rows };
    }
    var model = categoryModel(table, b, rows, ctx);
    ctx.otherCount = model.other.length;
    var labels = categoryLabels(table, b, model.keys, ctx);
    fig.option =
      fig.kind === "donut"
        ? donut(fig, b, model, labels, payload, sel || hl)
        : cartesian(fig, b, model, labels, payload, sel || hl);
    return { figure: fig, keys: model.keys, other: model.other, labels: labels, series: model.series };
  }

  // Filters as the page holds them (value lists become lookup sets).
  function prepare(filters) {
    var out = {};
    for (var col in filters) {
      if (!Object.prototype.hasOwnProperty.call(filters, col)) continue;
      var f = filters[col];
      var g = { type: f.type, source: f.source || null, mode: f.mode || "filter" };
      if (f.type === "range") {
        g.lo = f.lo;
        g.hi = f.hi;
      } else {
        g.values = f.values.slice();
        g.set = {};
        f.values.forEach(function (v) {
          g.set[v === null ? "\u0000null" : v] = 1;
        });
      }
      out[col] = g;
    }
    return out;
  }

  // ------------------------------------------------------------- the page

  function el(tag, cls, text) {
    var e = root.document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function mount(container, payload) {
    var doc = root.document;
    var tsj = root.tabsight;
    var table = new Table(payload.data);
    var state = {}; // col -> {type, values|lo,hi, source, mode}
    var tiles = [];
    var known = {};
    payload.filters.forEach(function (f) {
      known[f.col] = f;
    });

    // Header, filter bar and chips
    var bar = el("div", "ts-filters");
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", "Filters");
    var chips = el("div", "ts-chips");
    chips.setAttribute("aria-live", "polite");
    container.appendChild(bar);
    container.appendChild(chips);
    var grid = el("div", "ts-grid");
    container.appendChild(grid);
    var controls = {};

    function label(col, key) {
      if (key === null) return payload.unknown;
      if (key === OTHER_KEY) return payload.other;
      var l = table.labels[col];
      return l ? l.full[key] || key : String(key);
    }
    function title(col) {
      return (table.meta[col] && table.meta[col].title) || col;
    }

    payload.filters.forEach(function (f) {
      var box = el("div", "ts-filter");
      if (f.type === "range") {
        var name = el("span", "ts-filter__name", f.title);
        var from = el("select");
        var to = el("select");
        from.setAttribute("aria-label", f.title + " from");
        to.setAttribute("aria-label", f.title + " to");
        f.values.forEach(function (k, i) {
          var a = el("option", null, label(f.col, k));
          a.value = String(i);
          from.appendChild(a);
          var z = el("option", null, label(f.col, k));
          z.value = String(i);
          to.appendChild(z);
        });
        from.value = "0";
        to.value = String(f.values.length - 1);
        var onRange = function () {
          var lo = parseInt(from.value, 10);
          var hi = parseInt(to.value, 10);
          if (lo > hi) {
            var t = lo;
            lo = hi;
            hi = t;
          }
          if (lo === 0 && hi === f.values.length - 1) delete state[f.col];
          else state[f.col] = { type: "range", lo: f.values[lo], hi: f.values[hi], source: null };
          update();
        };
        from.addEventListener("change", onRange);
        to.addEventListener("change", onRange);
        box.appendChild(name);
        box.appendChild(from);
        box.appendChild(el("span", "ts-filter__to", "–"));
        box.appendChild(to);
        controls[f.col] = { from: from, to: to, filter: f };
      } else {
        var details = el("details", "ts-filter__menu");
        var summary = el("summary", null, f.title);
        details.appendChild(summary);
        var list = el("div", "ts-filter__list");
        var boxes = [];
        f.values.forEach(function (k) {
          var row = el("label", "ts-filter__item");
          var cb = el("input");
          cb.type = "checkbox";
          cb.checked = false;
          cb.addEventListener("change", function () {
            var chosen = boxes
              .filter(function (b) {
                return b.cb.checked;
              })
              .map(function (b) {
                return b.key;
              });
            if (chosen.length) state[f.col] = { type: "in", values: chosen, source: null };
            else delete state[f.col];
            update();
          });
          row.appendChild(cb);
          row.appendChild(doc.createTextNode(" " + label(f.col, k)));
          list.appendChild(row);
          boxes.push({ cb: cb, key: k });
        });
        details.appendChild(list);
        box.appendChild(details);
        controls[f.col] = { boxes: boxes, summary: summary, filter: f };
      }
      bar.appendChild(box);
    });

    function syncControls() {
      for (var col in controls) {
        var c = controls[col];
        var s = state[col];
        if (c.boxes) {
          var set = {};
          if (s && s.type === "in" && !s.source) {
            s.values.forEach(function (v) {
              set[v === null ? "\u0000null" : v] = 1;
            });
          }
          c.boxes.forEach(function (b) {
            b.cb.checked = set.hasOwnProperty(b.key === null ? "\u0000null" : b.key);
          });
          c.summary.textContent = c.filter.title + (s && !s.source ? ": " + s.values.length + " selected" : ": all");
        } else {
          var vals = c.filter.values;
          c.from.value = String(s && s.type === "range" ? Math.max(0, vals.indexOf(s.lo)) : 0);
          c.to.value = String(s && s.type === "range" ? Math.max(0, vals.indexOf(s.hi)) : vals.length - 1);
        }
      }
    }

    function drawChips() {
      chips.textContent = "";
      var any = false;
      Object.keys(state).forEach(function (col) {
        var s = state[col];
        any = true;
        var text =
          s.type === "range"
            ? title(col) + ": " + label(col, s.lo) + " – " + label(col, s.hi)
            : title(col) + ": " + s.values.map(function (v) {
                return label(col, v);
              }).join(", ");
        if (s.mode === "highlight") text += " (highlight)";
        var chip = el("span", "ts-chip");
        chip.appendChild(el("span", null, text.length > 120 ? text.slice(0, 117) + "…" : text));
        var x = el("button", "ts-chip__x", "×");
        x.type = "button";
        x.setAttribute("aria-label", "Remove filter " + title(col));
        x.addEventListener("click", function () {
          delete state[col];
          update();
        });
        chip.appendChild(x);
        chips.appendChild(chip);
      });
      if (any) {
        var reset = el("button", "ts-reset", payload.words.reset);
        reset.type = "button";
        reset.addEventListener("click", function () {
          state = {};
          update();
        });
        chips.appendChild(reset);
      }
    }

    // Tiles
    payload.tiles.forEach(function (tile) {
      var fig = tile.figure;
      var box = el("section", "ts-tile ts-dash-tile");
      box.style.gridColumn = "span " + Math.max(1, Math.min(12, tile.w || 6));
      var head = el("header", "ts-tile__head");
      head.appendChild(el("h2", "ts-tile__title", fig.title));
      if (fig.subtitle) head.appendChild(el("p", "ts-tile__subtitle", fig.subtitle));
      var menu = el("button", "ts-tile__csv", payload.words.csv);
      menu.type = "button";
      head.appendChild(menu);
      box.appendChild(head);
      var body = el("div", "ts-tile__body");
      var target = el("div", "ts-chart");
      target.setAttribute("role", "img");
      target.setAttribute("aria-label", fig.title);
      if (fig.kind !== "kpi" && fig.kind !== "table") target.style.height = fig.height + "px";
      body.appendChild(target);
      var notes = el("div", "ts-tile__notes");
      body.appendChild(notes);
      var status = el("p", "ts-tile__status");
      body.appendChild(status);
      box.appendChild(body);
      grid.appendChild(box);
      var t = { tile: tile, target: target, notes: notes, status: status, chart: null, keys: [], other: [], drawn: false, result: null };
      menu.addEventListener("click", function () {
        downloadCsv(t);
      });
      tiles.push(t);
    });

    function showNotes(t, filtered) {
      t.notes.textContent = "";
      var list = t.tile.figure.notes || [];
      if (!filtered) {
        list.forEach(function (n) {
          t.notes.appendChild(el("p", "ts-note", n));
        });
      } else if (t.other && t.other.length) {
        t.notes.appendChild(el("p", "ts-note", "Other groups " + t.other.length + " values (filtered)"));
      }
      t.status.textContent = "";
      if (t.tile.static) {
        t.status.textContent = Object.keys(state).length ? "Not affected by filters: " + t.tile.static : "";
      } else if (filtered) {
        t.status.textContent = payload.words.current;
      }
    }

    function render(t) {
      var tile = t.tile;
      var filtered = Object.keys(state).length > 0;
      var fig = tile.figure;
      var result = null;
      if (tile.binding) {
        result = compute(payload, table, tile, prepare(state));
        t.keys = result.keys;
        t.other = result.other || [];
        t.result = result;
        // Unfiltered, the tile shows exactly what Python drew (with any trend or forecast).
        if (filtered) fig = result.figure;
      }
      showNotes(t, filtered && !!tile.binding);
      if (fig.kind === "kpi" || fig.kind === "table") {
        tsj.render(t.target, fig);
        if (fig.kind === "table" && tile.binding) bindTable(t);
        return;
      }
      var option = tsj.hydrate(fig.option, fig.locales || payload.locales);
      var aspects = tsj.fitAspects(option);
      if (!t.chart) {
        tsj.registerMaps(fig.maps);
        t.chart = root.echarts.init(t.target, null, { renderer: "canvas" });
        t.chart.on("click", function (p) {
          onClick(t, p);
        });
        if (typeof root.ResizeObserver === "function") {
          new root.ResizeObserver(function () {
            t.chart.resize();
            tsj.fitMaps(t.chart, t.aspects);
          }).observe(t.target);
        }
      }
      t.aspects = aspects;
      t.chart.setOption(option, { notMerge: true });
      tsj.fitMaps(t.chart, aspects);
    }

    function bindTable(t) {
      var body = t.target.querySelector("tbody");
      if (!body) return;
      Array.prototype.forEach.call(body.querySelectorAll("tr"), function (tr, i) {
        tr.tabIndex = 0;
        tr.style.cursor = "pointer";
        var go = function (ev) {
          pick(t, t.keys[i], ev.ctrlKey || ev.metaKey || ev.shiftKey);
        };
        tr.addEventListener("click", go);
        tr.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            go(ev);
          }
        });
      });
    }

    function onClick(t, p) {
      var b = t.tile.binding;
      if (!b || !b.click || t.tile.action === "none") return;
      var ev = p.event && p.event.event ? p.event.event : {};
      var add = !!(ev.ctrlKey || ev.metaKey || ev.shiftKey);
      if (b.shape === "geo") {
        var raws = [];
        for (var raw in b.shapes) if (b.shapes[raw] === p.name) raws.push(raw);
        if (raws.length) pickMany(t, raws, add);
        return;
      }
      if (p.componentType !== "series" || p.dataIndex === undefined) return;
      var key = t.keys[p.dataIndex];
      if (key === undefined) return;
      if (key === OTHER_KEY) pickMany(t, t.other, add);
      else pick(t, key, add);
    }

    function pick(t, key, add) {
      pickMany(t, [key], add);
    }

    // Click semantics (PLAN 5.6): a click filters to that value; clicking it again removes
    // the filter; Ctrl/Shift + click adds or removes values.
    function pickMany(t, keys, add) {
      var col = t.tile.binding.click;
      var mode = t.tile.action === "highlight" ? "highlight" : "filter";
      var cur = state[col];
      var values = cur && cur.type === "in" && cur.source === t.tile.id ? cur.values.slice() : [];
      var same =
        values.length === keys.length &&
        keys.every(function (k) {
          return values.indexOf(k) >= 0;
        });
      if (add) {
        keys.forEach(function (k) {
          var i = values.indexOf(k);
          if (i >= 0) values.splice(i, 1);
          else values.push(k);
        });
      } else {
        values = same ? [] : keys.slice();
      }
      if (values.length) state[col] = { type: "in", values: values, source: t.tile.id, mode: mode };
      else delete state[col];
      update();
    }

    function downloadCsv(t) {
      var b = t.tile.binding;
      var lines = [];
      var cell = function (v) {
        var s = v === null || v === undefined ? "" : String(v);
        if (payload.csv_safe !== false && typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
        return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      if (!b) {
        lines.push(cell("This tile is drawn from all the data; its CSV comes from Python (fig.to_dict())."));
      } else if (t.result && t.result.rows) {
        lines.push(b.dims.map(title).concat(b.measures.map(function (m) { return m.label; })).map(cell).join(","));
        t.result.rows.forEach(function (row) {
          lines.push(row.keys.map(function (k, i) { return cell(label(b.dims[i], k)); }).concat(row.values.map(cell)).join(","));
        });
      } else if (t.result && t.result.series) {
        var head = [title(b.dims[0])];
        if (b.dims[1]) head.push(title(b.dims[1]));
        head.push(b.measures[0].label);
        lines.push(head.map(cell).join(","));
        t.result.series.forEach(function (s) {
          s.values.forEach(function (v, i) {
            var row = [t.result.labels[i]];
            if (b.dims[1]) row.push(s.name);
            row.push(v);
            lines.push(row.map(cell).join(","));
          });
        });
      } else {
        var fig = t.result ? t.result.figure : t.tile.figure;
        lines.push(cell(fig.title));
        if (fig.kpi) lines.push(cell(fig.kpi.value_full || fig.kpi.value_text));
      }
      var blob = new root.Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
      var a = el("a");
      a.href = root.URL.createObjectURL(blob);
      a.download = (t.tile.figure.title || "tile").replace(/[^\w\- ]+/g, "").slice(0, 60) + ".csv";
      doc.body.appendChild(a);
      a.click();
      setTimeout(function () {
        root.URL.revokeObjectURL(a.href);
        a.remove();
      }, 0);
    }

    // The address keeps the filters (#f=...), so a link opens the same view. What it
    // holds is checked against the table's known values; nothing else is accepted.
    function saveHash() {
      try {
        var cols = Object.keys(state);
        var text = cols.length ? "#f=" + encodeURIComponent(JSON.stringify(state)) : " ";
        root.history.replaceState(null, "", text === " " ? root.location.pathname + root.location.search : text);
      } catch (e) {
        /* sandboxed frames may not allow it */
      }
    }

    function loadHash() {
      var h;
      try {
        h = root.location.hash || "";
      } catch (e) {
        return;
      }
      if (h.indexOf("#f=") !== 0 || h.length > 20000) {
        state = {};
        return;
      }
      var raw;
      try {
        raw = JSON.parse(decodeURIComponent(h.slice(3)));
      } catch (e) {
        return;
      }
      state = sanitize(raw, table, payload);
    }

    var lazy = typeof root.IntersectionObserver === "function"
      ? new root.IntersectionObserver(function (entries) {
          entries.forEach(function (e) {
            if (!e.isIntersecting) return;
            var t = tiles.filter(function (x) {
              return x.target === e.target;
            })[0];
            if (t && !t.drawn) {
              t.drawn = true;
              render(t);
            }
          });
        }, { rootMargin: "200px" })
      : null;

    var insightNote = doc.querySelector(".ts-dash-insights__scope");

    function update() {
      if (insightNote) {
        insightNote.textContent = Object.keys(state).length
          ? "These describe all the data, not the current filters."
          : payload.words.all_data;
      }
      syncControls();
      drawChips();
      saveHash();
      tiles.forEach(function (t) {
        if (t.drawn) render(t);
      });
    }

    loadHash();
    syncControls();
    drawChips();
    tiles.forEach(function (t) {
      if (lazy) lazy.observe(t.target);
      else {
        t.drawn = true;
        render(t);
      }
    });
    // Filter lists close on a click elsewhere or Escape, like a native menu.
    var closeMenus = function (except) {
      Array.prototype.forEach.call(bar.querySelectorAll("details[open]"), function (d) {
        if (d !== except) d.open = false;
      });
    };
    doc.addEventListener("click", function (ev) {
      var inside = ev.target && ev.target.closest ? ev.target.closest("details") : null;
      closeMenus(inside);
    });
    doc.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") closeMenus(null);
    });
    // A link pasted into the address bar of an open page applies too.
    root.addEventListener("hashchange", function () {
      var before = JSON.stringify(state);
      loadHash();
      if (JSON.stringify(state) !== before) update();
    });
    // Before printing, draw every tile so none prints blank.
    root.addEventListener("beforeprint", function () {
      tiles.forEach(function (t) {
        if (!t.drawn) {
          t.drawn = true;
          render(t);
        }
      });
    });
    var api = {
      state: function () {
        return clone(state);
      },
      set: function (s) {
        state = sanitize(s, table, payload);
        update();
      },
      tiles: tiles,
    };
    root.tabsightDashboard.page = api; // for scripts and tests on this page
    return api;
  }

  // Keep only filters on known columns with known values (address bar input is untrusted).
  function sanitize(raw, table, payload) {
    var out = {};
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
    var sources = {};
    payload.tiles.forEach(function (t) {
      sources[t.id] = 1;
    });
    for (var col in raw) {
      if (!Object.prototype.hasOwnProperty.call(raw, col) || !table.dims[col] || col.indexOf("__") === 0) continue;
      var f = raw[col];
      if (!f || typeof f !== "object") continue;
      var known = table.known(col);
      var source = typeof f.source === "string" && sources[f.source] ? f.source : null;
      var mode = f.mode === "highlight" ? "highlight" : "filter";
      if (f.type === "range" && known.indexOf(f.lo) >= 0 && known.indexOf(f.hi) >= 0 && f.lo !== null && f.hi !== null) {
        out[col] = { type: "range", lo: f.lo, hi: f.hi, source: null, mode: "filter" };
      } else if (f.type === "in" && Array.isArray(f.values)) {
        var values = f.values.filter(function (v) {
          return known.indexOf(v) >= 0;
        });
        if (values.length) out[col] = { type: "in", values: values, source: source, mode: mode };
      }
    }
    return out;
  }

  root.tabsightDashboard = {
    mount: mount,
    compute: compute,
    prepare: prepare,
    sanitize: sanitize,
    Table: Table,
    naturalCompare: naturalCompare,
    OTHER_KEY: OTHER_KEY,
  };
})(typeof window !== "undefined" ? window : globalThis);
