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

  // Lookup tables keyed by data values have no prototype, so a category called
  // "constructor", "hasOwnProperty" or "__proto__" is an ordinary key.
  function dict() {
    return Object.create(null);
  }
  function has(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
  }
  // The colour pinned to a value ("constructor" is a value here, not Object's constructor).
  function colorOf(payload, name) {
    return payload.colors && has(payload.colors, name) ? payload.colors[name] : undefined;
  }
  // A prototype-free copy of a JSON object (one level), for tables read by data keys.
  function own(obj) {
    var out = dict();
    if (obj) Object.keys(obj).forEach(function (k) { out[k] = obj[k]; });
    return out;
  }

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
    this.dims = own(data.dims);
    this.nums = own(data.nums);
    this.lists = own(data.lists);
    this.meta = own(data.meta);
    this.labels = dict();
    var labels = data.labels || {};
    for (var col in labels) {
      if (has(labels, col)) this.labels[col] = { full: own(labels[col].full), compact: own(labels[col].compact) };
    }
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
      if (f.mode === "highlight" || col === ignoreCol || !table.dims[col]) continue;
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
        else ok = has(g.set, key === null ? "\u0000null" : key);
      }
      if (ok) out.push(r);
    }
    return out;
  }

  function newParts() {
    return { rows: 0, acc: {}, min: {}, max: {}, lists: {} };
  }

  function addRow(table, parts, r, measures) {
    parts.rows += table.nums.__rows[r] || 0;
    measures.forEach(function (m) {
      for (var p in m.parts) {
        var col = m.parts[p];
        if (p === "values") {
          var list = table.lists[col][r];
          if (list && list.length) parts.lists[col] = (parts.lists[col] || []).concat(list);
          continue;
        }
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
    for (k in from.lists) into.lists[k] = (into.lists[k] || []).concat(from.lists[k]);
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
    var values = parts.lists[P.values] || [];
    if (m.agg === "countd") {
      var seen = dict();
      var n = 0;
      values.forEach(function (v) {
        if (!has(seen, v)) {
          seen[v] = 1;
          n++;
        }
      });
      return n;
    }
    if (m.agg === "median") {
      if (!values.length) return null;
      var sorted = values.slice().sort(function (a, c) {
        return a - c;
      });
      var mid = Math.floor(sorted.length / 2);
      return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    }
    return null;
  }

  // Group the given rows by `dims`: {id -> {keys, parts}} plus the ids in first-seen order.
  function group(table, rows, dims, measures) {
    var groups = dict();
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
    return m.agg === "sum" || m.agg === "count" || m.agg === "countd";
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
        var keep = dict();
        ranked.slice(0, b.top).forEach(function (k) {
          keep[k === null ? "\u0000null" : k] = 1;
        });
        other = ranked.slice(b.top).sort(naturalCompare);
        xs = ranked.slice(0, b.top).concat([OTHER_KEY]);
        ctx.otherSet = dict();
        other.forEach(function (k) {
          ctx.otherSet[k === null ? "\u0000null" : k] = 1;
        });
        ctx.keep = keep;
      }
    }
    var inOther = function (k) {
      return ctx.otherSet && has(ctx.otherSet, k === null ? "\u0000null" : k);
    };
    // Cells: (x, colour) -> parts, with the Other members merged into one x.
    var cells = dict();
    var colours = [];
    var seenColour = dict();
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
      if (b.periods && b.missing && b.missing !== "connect" && xs.length) {
        var lo = b.periods.indexOf(xs[0]);
        var hi = b.periods.indexOf(xs[xs.length - 1]);
        if (lo >= 0 && hi >= lo) xs = b.periods.slice(lo, hi + 1);
      }
    } else if (b.sort === "order" && b.order) {
      var pos = dict();
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
      var total = dict();
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
      if (!b.time || !b.missing || b.missing === "connect") return null;
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
    return set && !has(set, key === null ? "\u0000null" : key);
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
        color = colorOf(payload, s.name) || (base.itemStyle && base.itemStyle.color);
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
        itemStyle: { color: k === OTHER_KEY ? payload.other_color : colorOf(payload, labels[i]) || payload.other_color },
      };
      if (set && dimmed(set, k) && k !== OTHER_KEY) item.itemStyle.opacity = 0.3;
      return item;
    });
    return opt;
  }

  function geo(fig, b, table, rows, ctx, sel) {
    var opt = clone(fig.option);
    var m = b.measures[0];
    var byShape = dict();
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
    var selectedShapes = dict();
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
    var firstTotals = dict();
    list.forEach(function (row) {
      var k = JSON.stringify(row.keys[0]);
      var v = row.values[0];
      firstTotals[k] = (firstTotals[k] || 0) + (v === null || v === undefined ? 0 : v);
    });
    var pos = dict();
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

  // ------------------------------------------------------------- more kinds
  // Each mirrors its Python builder in tabsight/charts (parts.py, extra.py, grids.py,
  // relation.py, maps.py); tests/test_dashboard.py checks them against Python.

  function pct0(x) {
    return String(Math.round(x * 100)) + "%";
  }

  function pct1(x) {
    return (Math.round(x * 1000) / 10).toFixed(1) + "%";
  }

  function niceCeiling(value) {
    if (value <= 0) return 1;
    var power = Math.pow(10, Math.floor(Math.log10(value)));
    var steps = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * power >= value) return steps[i] * power;
    return 10 * power;
  }

  // (low, high, colours) for a colour scale, as _common.scale does.
  function colourScale(values, ramps) {
    var nums = values.filter(function (v) {
      return v !== null && v !== undefined;
    });
    var lo = nums.length ? Math.min.apply(null, nums) : 0;
    var hi = nums.length ? Math.max.apply(null, nums) : 1;
    var diverging = lo < 0 && hi > 0;
    if (diverging) {
      var bound = Math.max(-lo, hi);
      lo = -bound;
      hi = bound;
    }
    if (hi === lo) hi = lo + (Math.abs(lo) || 1);
    return { lo: lo, hi: hi, ramp: diverging ? ramps.div : ramps.seq };
  }

  function setScale(opt, m, ctx, s) {
    var vm = opt.visualMap;
    if (!vm) return;
    vm.min = s.lo;
    vm.max = s.hi;
    if (vm.inRange) vm.inRange.color = s.ramp;
    var tsj = root.tabsight;
    vm.text = [tsj.formatNumber(s.hi, m.compact, ctx.locales), tsj.formatNumber(s.lo, m.compact, ctx.locales)];
  }

  function keyLabel(table, col, k, ctx, compact) {
    if (k === OTHER_KEY) return ctx.other + " (" + ctx.otherCount + ")";
    if (k === null) return ctx.unknown;
    var l = table.labels[col];
    if (l) return (compact ? l.compact[k] : l.full[k]) || k;
    return String(k);
  }

  function goalValues(table, rows, b, model, ctx) {
    if (b.goal_measure) {
      var gm = model.series[1];
      return gm ? gm.values : [];
    }
    return model.keys.map(function () {
      return b.goal === undefined ? null : b.goal;
    });
  }

  function bulletTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var measures = b.goal_measure ? [b.measures[0], b.goal_measure] : [b.measures[0]];
    var nb = Object.assign({}, b, { measures: measures });
    var model = categoryModel(table, nb, rows, ctx);
    var labels = model.keys.map(function (k) {
      return keyLabel(table, b.dims[0], k, ctx, false);
    });
    var actual = model.series[0].values;
    var goals = goalValues(table, rows, b, model, ctx);
    var tsj = root.tabsight;
    opt.yAxis.data = labels;
    opt.series[0].data = goals;
    opt.series[1].data = actual.map(function (a, i) {
      var item = { value: a };
      var g = goals[i];
      if (g !== null && g !== undefined) {
        var share = a !== null && g ? " (" + pct0(a / g) + " of it)" : "";
        item.note = "goal " + tsj.formatNumber(g, b.measures[0].full, ctx.locales) + share;
      }
      return item;
    });
    opt.series[2].data = goals;
    return { option: opt, keys: model.keys, model: model, labels: labels };
  }

  function bulletValue(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var parts = newParts();
    var measures = b.goal_measure ? [b.measures[0], b.goal_measure] : [b.measures[0]];
    rows.forEach(function (r) {
      addRow(table, parts, r, measures);
    });
    var a = rows.length ? finish(parts, b.measures[0], ctx.minGroup) : null;
    var g = b.goal_measure ? (rows.length ? finish(parts, b.goal_measure, ctx.minGroup) : null) : b.goal;
    var tsj = root.tabsight;
    var item = { value: a };
    if (g !== null && g !== undefined) {
      item.note = "goal " + tsj.formatNumber(g, b.measures[0].full, ctx.locales) + (a !== null && g ? " (" + pct0(a / g) + " of it)" : "");
    }
    opt.series[0].data = [g];
    opt.series[1].data = [item];
    opt.series[2].data = [g];
    return opt;
  }

  function gaugeTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var parts = newParts();
    var measures = b.goal_measure ? [b.measures[0], b.goal_measure] : [b.measures[0]];
    rows.forEach(function (r) {
      addRow(table, parts, r, measures);
    });
    var value = rows.length ? finish(parts, b.measures[0], ctx.minGroup) : null;
    var goal = b.goal_measure ? (rows.length ? finish(parts, b.goal_measure, ctx.minGroup) : null) : b.goal === undefined ? null : b.goal;
    var top = goal && goal > 0 ? goal : niceCeiling((value || 0) * 1.1);
    if (value !== null && value > top) top = niceCeiling(value * 1.05);
    var s = opt.series[0];
    s.max = top;
    s.data = [{ value: value, name: goal && value !== null ? pct0(value / goal) + " of goal" : "" }];
    return opt;
  }

  function funnelTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var model = categoryModel(table, Object.assign({}, b, { top: null }), rows, ctx);
    var list = model.keys.map(function (k, i) {
      var v = model.series[0].values[i];
      return { key: k, name: k === null ? ctx.unknown : String(k), value: v === null ? 0 : v };
    });
    if (!b.keep_order) {
      list.sort(function (a, c) {
        return c.value - a.value;
      });
    }
    var first = list.length ? list[0].value : 0;
    opt.series[0].data = list.map(function (r, i) {
      var note = "";
      if (i > 0 && list[i - 1].value) note = pct0(r.value / list[i - 1].value) + " of the previous stage";
      if (i && first) note += (note ? "; " : "") + pct0(r.value / first) + " of the first";
      var item = { name: r.name, value: r.value, itemStyle: { color: b.palette[i % b.palette.length] } };
      if (note) item.note = note;
      return item;
    });
    return { option: opt, keys: list.map(function (r) { return r.key; }) };
  }

  function paretoTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var model = categoryModel(table, b, rows, ctx);
    ctx.otherCount = model.other.length;
    var labels = model.keys.map(function (k) {
      return k === OTHER_KEY ? ctx.other + " (" + model.other.length + ")" : k === null ? ctx.unknown : String(k);
    });
    var values = model.series[0].values.map(function (v) {
      return v === null ? 0 : v;
    });
    var total = values.reduce(function (a, v) { return a + v; }, 0) || 1;
    var running = 0;
    var cumulative = values.map(function (v) {
      running += v;
      return Math.round((running / total) * 1e6) / 1e6;
    });
    opt.xAxis.data = labels;
    opt.series[0].data = values;
    opt.series[1].data = cumulative;
    return { option: opt, keys: model.keys, other: model.other, model: model, labels: labels };
  }

  function waterfallTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var model = categoryModel(table, Object.assign({}, b, { top: null, missing: "connect" }), rows, ctx);
    var labels = model.keys.map(function (k) {
      return keyLabel(table, b.dims[0], k, ctx, model.keys.length > 8 && /\|(month|day)$/.test(b.dims[0]));
    });
    var data = [];
    var running = 0;
    model.series[0].values.forEach(function (v, i) {
      var change = v === null ? 0 : v;
      var lo = running;
      var hi = running + change;
      running = hi;
      data.push({ name: labels[i], value: [i, lo, hi, change, running], itemStyle: { color: change >= 0 ? b.colors.pos : b.colors.neg } });
    });
    var template = fig.option.series[0].data;
    if (b.total) {
      var last = template[template.length - 1];
      labels = labels.concat(["Total"]);
      data.push({ name: "Total", value: [data.length, 0, running, running, running], itemStyle: clone(last.itemStyle) });
    }
    opt.xAxis.data = labels;
    opt.series[0].data = data;
    return { option: opt, keys: model.keys };
  }

  // Rows of a two-dimension grid in Python's order: by the first dimension's rule, then natural.
  function heatmapTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var model = categoryModel(table, Object.assign({}, b, { top: null, missing: "connect" }), rows, ctx);
    var cells = group(table, rows, b.dims, b.measures);
    var byX = dict();
    cells.order.forEach(function (id) {
      var g = cells.groups[id];
      var xk = JSON.stringify(g.keys[0]);
      (byX[xk] = byX[xk] || []).push(g);
    });
    var rowKeys = [];
    var sortedCells = [];
    var seen = dict();
    var rowTime = /\|[a-z]+$/.test(b.dims[1]);
    model.keys.forEach(function (xk) {
      var list = (byX[JSON.stringify(xk)] || []).slice();
      list.sort(function (a, c) {
        var x = a.keys[1];
        var y = c.keys[1];
        if (rowTime) return x < y ? -1 : x > y ? 1 : 0;
        return naturalCompare(x, y);
      });
      list.forEach(function (g) {
        sortedCells.push(g);
        var id = JSON.stringify(g.keys[1]);
        if (!seen[id]) {
          seen[id] = 1;
          rowKeys.push(g.keys[1]);
        }
      });
    });
    var xLabels = model.keys.map(function (k) {
      return keyLabel(table, b.dims[0], k, ctx, model.keys.length > 8 && /\|(month|day)$/.test(b.dims[0]));
    });
    var rowLabels = rowKeys.map(function (k) {
      return keyLabel(table, b.dims[1], k, ctx, false);
    });
    var xi = dict();
    model.keys.forEach(function (k, i) {
      xi[JSON.stringify(k)] = i;
    });
    var yi = dict();
    rowKeys.forEach(function (k, i) {
      yi[JSON.stringify(k)] = i;
    });
    var data = [];
    sortedCells.forEach(function (g) {
      var i = xi[JSON.stringify(g.keys[0])];
      var j = yi[JSON.stringify(g.keys[1])];
      data.push({ value: [i, j, finish(g.parts, b.measures[0], ctx.minGroup)], name: rowLabels[j] + " · " + xLabels[i] });
    });
    opt.xAxis.data = xLabels;
    opt.yAxis.data = rowLabels;
    opt.series[0].data = data;
    opt.series[0].label.show = data.length <= b.labelled_up_to;
    setScale(opt, b.measures[0], ctx, colourScale(data.map(function (d) { return d.value[2]; }), b.ramps));
    return { option: opt, keys: model.keys };
  }

  // Groups in aggregate()'s default order: by the first field's total (largest first),
  // ties and the other fields in natural order. Python's stable sorts start from this.
  function aggregateOrder(table, rows, dims, measures, ctx) {
    var cells = group(table, rows, dims, measures);
    var list = cells.order.map(function (id) {
      var g = cells.groups[id];
      return { keys: g.keys, parts: g.parts, value: finish(g.parts, measures[0], ctx.minGroup) };
    });
    var totals = dict();
    list.forEach(function (g) {
      var k = JSON.stringify(g.keys[0]);
      totals[k] = (totals[k] || 0) + (g.value === null ? 0 : g.value);
    });
    list.sort(function (a, c) {
      var d = totals[JSON.stringify(c.keys[0])] - totals[JSON.stringify(a.keys[0])];
      if (d) return d;
      for (var i = 0; i < a.keys.length; i++) {
        d = naturalCompare(a.keys[i], c.keys[i]);
        if (d) return d;
      }
      return 0;
    });
    return list;
  }

  function treeTile(fig, b, table, rows, ctx, payload) {
    var opt = clone(fig.option);
    var leaves = aggregateOrder(table, rows, b.dims, b.measures, ctx).filter(function (g) {
      return g.value !== null && g.value > 0;
    });
    if (leaves.length > b.max_leaves) {
      leaves.sort(function (a, c) { return c.value - a.value; });
      leaves = leaves.slice(0, b.max_leaves);
    }
    var total = leaves.reduce(function (a, l) { return a + l.value; }, 0) || 1;
    var rootNode = { children: dict(), order: [] };
    leaves.forEach(function (l) {
      var node = rootNode;
      l.keys.forEach(function (k) {
        var label = k === null ? "Unknown" : String(k);
        if (!node.children[label]) {
          node.children[label] = { name: label, value: 0, children: dict(), order: [] };
          node.order.push(label);
        }
        node = node.children[label];
        node.value += l.value;
      });
    });
    var emit = function (node, depth, color) {
      var item = { name: node.name, value: Math.round(node.value * 1e10) / 1e10, note: pct1(node.value / total) + " of the total" };
      if (depth === 0) color = colorOf(payload, node.name) || payload.other_color;
      if (color) item.itemStyle = { color: color };
      var kids = node.order.map(function (k) { return node.children[k]; });
      kids.sort(function (a, c) { return c.value - a.value; });
      if (kids.length) item.children = kids.map(function (k) { return emit(k, depth + 1, color); });
      return item;
    };
    var top = rootNode.order.map(function (k) { return rootNode.children[k]; });
    top.sort(function (a, c) { return c.value - a.value; });
    opt.series[0].data = top.map(function (n) { return emit(n, 0, null); });
    return { option: opt, keys: top.map(function (n) { return n.name === "Unknown" ? null : n.name; }) };
  }

  function sankeyTile(fig, b, table, rows, ctx, payload) {
    var opt = clone(fig.option);
    var links = [];
    aggregateOrder(table, rows, b.dims, b.measures, ctx).forEach(function (g) {
      if (g.value === null || g.value <= 0) return;
      links.push([String(g.keys[0]), String(g.keys[1]), g.value]);
    });
    links.sort(function (a, c) { return c[2] - a[2]; });
    links = links.slice(0, b.max_links);
    var sources = dict();
    links.forEach(function (l) { sources[l[0]] = 1; });
    var fixed = links.map(function (l) {
      return [l[0], has(sources, l[1]) ? "→ " + l[1] : l[1], l[2]];
    });
    var nodes = [];
    var seen = dict();
    fixed.map(function (l) { return l[0]; }).concat(fixed.map(function (l) { return l[1]; })).forEach(function (n) {
      if (!seen[n]) {
        seen[n] = 1;
        nodes.push(n);
      }
    });
    var s = opt.series[0];
    s.data = nodes.map(function (n) {
      var bare = n.indexOf("→ ") === 0 ? n.slice(2) : n;
      return { name: n, itemStyle: { color: colorOf(payload, bare) || payload.other_color } };
    });
    s.links = fixed.map(function (l) { return { source: l[0], target: l[1], value: l[2] }; });
    return { option: opt, keys: [] };
  }

  function calendarTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var cells = group(table, rows, b.dims, b.measures);
    var days = [];
    cells.order.forEach(function (id) {
      var g = cells.groups[id];
      if (g.keys[0] === null) return;
      days.push({ key: g.keys[0], v: finish(g.parts, b.measures[0], ctx.minGroup) });
    });
    days.sort(function (a, c) { return a.key < c.key ? -1 : a.key > c.key ? 1 : 0; });
    var years = [];
    days.forEach(function (d) {
      var y = d.key.slice(0, 4);
      if (years.indexOf(y) < 0) years.push(y);
    });
    years = years.slice(-b.max_years);
    var labels = (table.labels[b.dims[0]] || {}).full || {};
    var data = days.filter(function (d) { return years.indexOf(d.key.slice(0, 4)) >= 0; }).map(function (d) {
      return { name: labels[d.key] || d.key, value: [d.key, d.v] };
    });
    var calTemplate = (Array.isArray(fig.option.calendar) ? fig.option.calendar : [fig.option.calendar])[0];
    var serTemplate = fig.option.series[0];
    opt.calendar = years.map(function (y, i) {
      var c = clone(calTemplate);
      c.top = 30 + i * 150;
      c.range = y;
      return c;
    });
    opt.series = years.map(function (y, i) {
      var s = clone(serTemplate);
      s.calendarIndex = i;
      s.data = data.filter(function (d) { return d.value[0].slice(0, 4) === y; });
      return s;
    });
    setScale(opt, b.measures[0], ctx, colourScale(data.map(function (d) { return d.value[1]; }), b.ramps));
    if (opt.visualMap) {
      opt.visualMap.seriesIndex = years.map(function (_, i) { return i; });
    }
    return { option: opt, keys: [] };
  }

  function histogramTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var counts = [];
    for (var i = 0; i < b.bins; i++) counts.push(0);
    var cells = group(table, rows, b.dims, b.measures);
    cells.order.forEach(function (id) {
      var g = cells.groups[id];
      if (g.keys[0] === null) return;
      counts[parseInt(g.keys[0], 10)] += g.parts.rows;
    });
    var lo = 0;
    var hi = counts.length - 1;
    while (lo < hi && counts[lo] === 0) lo++;
    while (hi > lo && counts[hi] === 0) hi--;
    var keys = [];
    for (var k = lo; k <= hi; k++) keys.push(String(k));
    opt.xAxis.data = keys.map(function (k2) { return b.labels[parseInt(k2, 10)]; });
    opt.series[0].data = keys.map(function (k2) {
      var j = parseInt(k2, 10);
      return { value: counts[j], note: b.notes[j] };
    });
    return { option: opt, keys: keys };
  }

  function bubbleSize(v, biggest) {
    return Math.round((6 + 34 * Math.sqrt(Math.abs(v) / (biggest || 1))) * 10) / 10;
  }

  function pointsTile(fig, b, table, rows, ctx, payload) {
    var opt = clone(fig.option);
    var model = categoryModel(table, Object.assign({}, b, { top: null, missing: "connect" }), rows, ctx);
    var cells = group(table, rows, b.dims, b.measures);
    var rowsOut = [];
    var byId = dict();
    cells.order.forEach(function (id) {
      byId[id] = cells.groups[id];
    });
    model.keys.forEach(function (xk) {
      cells.order.forEach(function (id) {
        var g = byId[id];
        if (JSON.stringify(g.keys[0]) !== JSON.stringify(xk)) return;
        rowsOut.push({ keys: g.keys, values: b.measures.map(function (m) { return finish(g.parts, m, ctx.minGroup); }) });
      });
    });
    var need = b.measures.length;
    var biggest = 1;
    if (need === 3) {
      biggest = 0;
      rowsOut.forEach(function (r) { biggest = Math.max(biggest, Math.abs(r.values[2] || 0)); });
      if (!biggest) biggest = 1;
    }
    var template = fig.option.series[0];
    var colourOf = b.dims.length > 1;
    var groups = dict();
    var names = [];
    rowsOut.forEach(function (r) {
      var name = colourOf ? (r.keys[1] === null ? ctx.unknown : String(r.keys[1])) : null;
      var id = String(name);
      if (!groups[id]) {
        groups[id] = { name: name, data: [] };
        names.push(id);
      }
      if (r.values[0] === null || r.values[1] === null) return;
      var item = { name: r.keys[0] === null ? ctx.unknown : String(r.keys[0]), value: r.values.slice() };
      if (need === 3) item.symbolSize = bubbleSize(r.values[2] || 0, biggest);
      groups[id].data.push(item);
    });
    names.sort();
    var labelled = rowsOut.length <= 20;
    opt.series = names.map(function (id) {
      var g = groups[id];
      var s = clone(template);
      s.name = g.name === null ? template.name : g.name;
      s.data = g.data;
      if (g.name !== null) s.itemStyle.color = colorOf(payload, g.name) || s.itemStyle.color;
      if (labelled) {
        s.label = s.label || { show: true, formatter: "{b}", position: "right", fontSize: 10, color: payload.theme.text_secondary };
      } else {
        delete s.label;
      }
      return s;
    });
    return { option: opt, keys: model.keys };
  }

  function pointsMapTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var m = b.measures[0];
    var cells = group(table, rows, b.dims, b.measures);
    var byPlace = dict();
    var order = [];
    cells.order.forEach(function (id) {
      var g = cells.groups[id];
      var p = g.keys[0] === null ? null : b.points[g.keys[0]];
      if (!p) return;
      if (!byPlace[p[0]]) {
        byPlace[p[0]] = { point: p, parts: newParts() };
        order.push(p[0]);
      }
      merge(byPlace[p[0]].parts, g.parts);
    });
    var kept = [];
    order.forEach(function (fid) {
      var e = byPlace[fid];
      var v = finish(e.parts, m, ctx.minGroup);
      if (v !== null) kept.push({ p: e.point, v: v });
    });
    kept.sort(function (a, c) { return Math.abs(c.v) - Math.abs(a.v); });
    kept = kept.slice(0, b.max_points);
    if (fig.kind === "density_map") {
      var peak = 0;
      kept.forEach(function (k) { peak = Math.max(peak, Math.abs(k.v)); });
      opt.series[0].data = kept.map(function (k) { return [k.p[1], k.p[2], Math.abs(k.v)]; });
      if (opt.visualMap) opt.visualMap.max = peak || 1;
      return { option: opt, keys: [] };
    }
    var biggest = 0;
    kept.forEach(function (k) { biggest = Math.max(biggest, Math.abs(k.v)); });
    biggest = biggest || 1;
    opt.series[0].data = kept.map(function (k) {
      return {
        name: k.p[3],
        value: [k.p[1], k.p[2], k.v],
        symbolSize: Math.round((5 + 25 * Math.sqrt(Math.abs(k.v) / biggest)) * 10) / 10,
        itemStyle: { color: k.v < 0 ? b.colors.neg : b.colors.pos },
      };
    });
    return { option: opt, keys: [] };
  }

  function flowsTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var cells = group(table, rows, b.dims, b.measures);
    var pairs = dict();
    var order = [];
    cells.order.forEach(function (id) {
      var g = cells.groups[id];
      var a = g.keys[0] === null ? null : b.places[g.keys[0]];
      var c = g.keys[1] === null ? null : b.places[g.keys[1]];
      if (!a || !c || a[0] === c[0]) return;
      var pid = a[0] + "\u0000" + c[0];
      if (!pairs[pid]) {
        pairs[pid] = { a: a, c: c, parts: newParts() };
        order.push(pid);
      }
      merge(pairs[pid].parts, g.parts);
    });
    var flows = [];
    order.forEach(function (pid) {
      var p = pairs[pid];
      var v = finish(p.parts, b.measures[0], ctx.minGroup);
      if (v !== null && v > 0) flows.push({ a: p.a, c: p.c, v: v });
    });
    flows.sort(function (x, y) { return y.v - x.v; });
    flows = flows.slice(0, b.max_flows);
    var biggest = 0;
    flows.forEach(function (f) { biggest = Math.max(biggest, f.v); });
    biggest = biggest || 1;
    var ends = dict();
    var endOrder = [];
    opt.series[0].data = flows.map(function (f) {
      [f.a, f.c].forEach(function (p) {
        if (!has(ends, p[3])) endOrder.push(p[3]);
        ends[p[3]] = [p[1], p[2]];
      });
      return {
        name: f.a[3] + " → " + f.c[3],
        coords: [[f.a[1], f.a[2]], [f.c[1], f.c[2]]],
        value: f.v,
        lineStyle: { width: Math.round((1 + (7 * f.v) / biggest) * 100) / 100 },
      };
    });
    if (opt.series[1]) {
      opt.series[1].data = endOrder.map(function (n) { return { name: n, value: ends[n] }; });
      if (opt.series[1].label) opt.series[1].label.show = endOrder.length <= 15;
    }
    return { option: opt, keys: [] };
  }

  function lollipop(opt, template, b) {
    var stem = opt.series.filter(function (x) {
      return x.type === "bar";
    })[0];
    var dot = clone(template.series.filter(function (x) {
      return x.type === "scatter";
    })[0]);
    if (!stem || !dot) return opt;
    dot.data = stem.data.map(function (d) {
      return d && typeof d === "object" ? d.value : d;
    });
    if (stem.label) {
      dot.label = stem.label;
      dot.label.position = b.horizontal ? "right" : "top";
      delete stem.label;
    } else {
      delete dot.label;
    }
    stem.data = stem.data.map(function (d) {
      return d && typeof d === "object" && d.itemStyle && d.itemStyle.color ? d.value : d;
    });
    opt.series.push(dot);
    return opt;
  }


  // numpy.percentile's default (linear) interpolation, including its rounding-safe lerp.
  function percentile(sorted, q) {
    var h = (sorted.length - 1) * q;
    var lo = Math.floor(h);
    var hi = Math.min(lo + 1, sorted.length - 1);
    var t = h - lo;
    var a = sorted[lo];
    var c = sorted[hi];
    var diff = c - a;
    return t >= 0.5 ? c - diff * (1 - t) : a + diff * t;
  }

  function boxTile(fig, b, table, rows, ctx) {
    var opt = clone(fig.option);
    var col = b.measures[0].parts.values;
    var groups = dict();
    var order = [];
    rows.forEach(function (r) {
      var k = b.dims.length ? table.key(b.dims[0], r) : b.name;
      var id = k === null ? ctx.unknown : String(k);
      if (!groups[id]) {
        groups[id] = [];
        order.push(id);
      }
      var list = table.lists[col][r];
      if (list && list.length) groups[id] = groups[id].concat(list);
    });
    order = order.filter(function (id) { return groups[id].length; });
    order.sort(function (a, c) { return groups[c].length - groups[a].length; });
    order = order.slice(0, b.max_boxes);
    var stats = order.map(function (id) {
      var v = groups[id].slice().sort(function (x, y) { return x - y; });
      var q1 = percentile(v, 0.25);
      var med = percentile(v, 0.5);
      var q3 = percentile(v, 0.75);
      var iqr = q3 - q1;
      var loF = q1 - 1.5 * iqr;
      var hiF = q3 + 1.5 * iqr;
      var inside = v.filter(function (x) { return x >= loF && x <= hiF; });
      var out = groups[id].filter(function (x) { return x < loF || x > hiF; }).slice(0, 200);
      return { id: id, box: [inside[0], q1, med, q3, inside[inside.length - 1]], n: v.length, out: out };
    });
    if (b.dims.length && b.order) {
      var pos = dict();
      b.order.forEach(function (k, i) { pos[k] = i; });
      stats.sort(function (a, c) {
        return (a.id in pos ? pos[a.id] : b.order.length) - (c.id in pos ? pos[c.id] : b.order.length);
      });
    } else if (b.dims.length) {
      stats.sort(function (a, c) { return c.box[2] - a.box[2]; });
    }
    opt.xAxis.data = stats.map(function (st) { return st.id; });
    opt.series[0].data = stats.map(function (st) {
      return { value: st.box, note: st.n.toLocaleString("en-US") + " rows" };
    });
    var outliers = [];
    stats.forEach(function (st, i) {
      st.out.forEach(function (v) { outliers.push([i, v]); });
    });
    opt.series[1].data = outliers;
    return { option: opt, keys: stats.map(function (st) { return st.id === ctx.unknown ? null : st.id; }) };
  }

  // Lines over a number: one point per x value, on a real value axis (relation.numeric_lines).
  function numericLinesTile(fig, b, table, rows, ctx, payload) {
    var opt = clone(fig.option);
    var cells = group(table, rows, b.dims, b.measures);
    var list = cells.order.map(function (id) { return cells.groups[id]; }).filter(function (g) { return g.keys[0] !== null; });
    list.sort(function (a, c) { return parseFloat(a.keys[0]) - parseFloat(c.keys[0]); });
    var colourOf = b.dims.length > 1;
    var names = [];
    var byName = dict();
    list.forEach(function (g) {
      var name = colourOf ? (g.keys[1] === null ? ctx.unknown : String(g.keys[1])) : null;
      var id = String(name);
      if (!byName[id]) {
        byName[id] = { name: name, cells: [] };
        names.push(id);
      }
      byName[id].cells.push(g);
    });
    names.sort();
    var template = fig.option.series[0];
    var single = names.length * b.measures.length === 1;
    var out = [];
    names.forEach(function (id) {
      var grp = byName[id];
      b.measures.forEach(function (m) {
        var s = clone(template);
        var label = grp.name !== null ? grp.name : m.label;
        var color = single ? template.itemStyle.color : colorOf(payload, label) || template.itemStyle.color;
        s.name = label;
        s.data = grp.cells.map(function (g) { return [parseFloat(g.keys[0]), finish(g.parts, m, ctx.minGroup)]; });
        s.showSymbol = s.data.length <= 40;
        s.lineStyle.color = color;
        s.itemStyle.color = color;
        if (s.areaStyle) s.areaStyle.color = color;
        delete s.markLine;
        delete s.markArea;
        delete s.markPoint;
        out.push(s);
      });
    });
    opt.series = out;
    var fmt = opt.tooltip && opt.tooltip.formatter && opt.tooltip.formatter.$tooltip;
    if (fmt) {
      fmt.series_fmt = {};
      out.forEach(function (s) { fmt.series_fmt[s.name] = b.measures[0].full; });
    }
    return { option: opt, keys: [] };
  }

  // ------------------------------------------------------------- analytics after filtering
  // Ports of tabsight/analytics.py and charts/pane.py, so trend lines, forecasts, reference
  // lines and outliers follow the filters instead of describing all the data.

  var GRID = [0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95];
  var Z95 = 1.96;

  function finiteList(values) {
    return values.filter(function (v) {
      return v !== null && v !== undefined && isFinite(v);
    });
  }

  function linearTrend(ys) {
    var xs = [];
    var vs = [];
    ys.forEach(function (y, i) {
      if (y !== null && y !== undefined && isFinite(y)) {
        xs.push(i);
        vs.push(y);
      }
    });
    if (vs.length < 3) return null;
    var n = vs.length;
    var mx = xs.reduce(function (a, v) { return a + v; }, 0) / n;
    var my = vs.reduce(function (a, v) { return a + v; }, 0) / n;
    var sxy = 0;
    var sxx = 0;
    for (var i = 0; i < n; i++) {
      sxy += (xs[i] - mx) * (vs[i] - my);
      sxx += (xs[i] - mx) * (xs[i] - mx);
    }
    if (!sxx) return null;
    var slope = sxy / sxx;
    var intercept = my - slope * mx;
    var total = 0;
    var resid = 0;
    for (var j = 0; j < n; j++) {
      total += (vs[j] - my) * (vs[j] - my);
      var f = intercept + slope * xs[j];
      resid += (vs[j] - f) * (vs[j] - f);
    }
    var r2 = total > 0 ? 1 - resid / total : 1;
    return { slope: slope, intercept: intercept, r2: Math.max(0, Math.min(1, r2)), n: n };
  }

  function hwRun(y, season, a, b, g) {
    var level;
    var trend;
    var seasonal = [];
    var start;
    if (season) {
      var first = 0;
      var second = 0;
      for (var i = 0; i < season; i++) {
        first += y[i];
        second += y[i + season];
      }
      first /= season;
      trend = (second / season - first) / season;
      var middle = (season - 1) / 2;
      for (var k = 0; k < season; k++) {
        seasonal.push((y[k] + y[k + season]) / 2 - (first + trend * (k - middle) + (trend * season) / 2));
      }
      level = first + trend * (season - 1 - middle);
      start = season;
    } else {
      level = y[0];
      trend = y[1] - y[0];
      start = 1;
    }
    var residuals = [];
    for (var t = start; t < y.length; t++) {
      var s = season ? seasonal[t % season] : 0;
      residuals.push(y[t] - (level + trend + s));
      var last = level;
      level = a * (y[t] - s) + (1 - a) * (level + trend);
      trend = b * (level - last) + (1 - b) * trend;
      if (season) seasonal[t % season] = g * (y[t] - level) + (1 - g) * s;
    }
    var sse = residuals.reduce(function (acc, r) { return acc + r * r; }, 0);
    return { sse: sse, residuals: residuals, level: level, trend: trend, seasonal: seasonal };
  }

  function forecast(ys, horizon, season) {
    if (ys.some(function (v) { return v === null || !isFinite(v); })) return { error: "a forecast needs a value for every period (no gaps)" };
    var need = season ? 2 * season : 6;
    if (ys.length < need) {
      return { error: "it needs " + (season ? "two full seasons (" + need + " periods)" : need + " periods") + ", and there are " + ys.length };
    }
    var best = null;
    GRID.forEach(function (a) {
      GRID.forEach(function (b) {
        (season ? GRID : [0]).forEach(function (g) {
          var sse = hwRun(ys, season, a, b, g).sse;
          if (best === null || sse < best[0] - 1e-9 * Math.max(1, best[0])) best = [sse, a, b, g];
        });
      });
    });
    var a = best[1];
    var b = best[2];
    var g = best[3];
    var run = hwRun(ys, season, a, b, g);
    var mean = run.residuals.reduce(function (x, v) { return x + v; }, 0) / (run.residuals.length || 1);
    var sigma = run.residuals.length
      ? Math.sqrt(run.residuals.reduce(function (x, v) { return x + (v - mean) * (v - mean); }, 0) / run.residuals.length)
      : 0;
    var n = ys.length;
    var values = [];
    var lower = [];
    var upper = [];
    var growth = 0;
    for (var h = 1; h <= horizon; h++) {
      var v = run.level + h * run.trend + (season ? run.seasonal[(n + h - 1) % season] : 0);
      if (h > 1) {
        var j = h - 1;
        var c = a * (1 + j * b) + (season && j % season === 0 ? g : 0);
        growth += c * c;
      }
      var spread = Z95 * sigma * Math.sqrt(1 + growth);
      values.push(v);
      lower.push(v - spread);
      upper.push(v + spread);
    }
    if (Math.min.apply(null, ys) >= 0 && Math.min.apply(null, lower) < 0) {
      values = values.map(function (v) { return Math.max(0, v); });
      lower = lower.map(function (v) { return Math.max(0, v); });
    }
    return { values: values, lower: lower, upper: upper };
  }

  function outlierMask(values, k) {
    var finite = finiteList(values);
    var mask = values.map(function () { return false; });
    if (finite.length < 4) return mask;
    var sorted = finite.slice().sort(function (x, y) { return x - y; });
    var q1 = percentile(sorted, 0.25);
    var q3 = percentile(sorted, 0.75);
    var fence = k * (q3 - q1);
    if (!fence) return mask;
    return values.map(function (v) {
      return v !== null && isFinite(v) && (v < q1 - fence || v > q3 + fence);
    });
  }

  function refValue(values, ref) {
    if (typeof ref === "number") return ref;
    var finite = finiteList(values);
    if (!finite.length) return null;
    if (ref === "mean") return finite.reduce(function (a, v) { return a + v; }, 0) / finite.length;
    var sorted = finite.slice().sort(function (x, y) { return x - y; });
    if (ref === "median") return percentile(sorted, 0.5);
    return percentile(sorted, parseInt(ref.slice(1), 10) / 100);
  }

  function refLabel(ref) {
    if (typeof ref === "number") return "Target";
    if (ref === "mean") return "Average";
    if (ref === "median") return "Median";
    var n = parseInt(ref.slice(1), 10);
    var suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
    return n + suffix + " percentile";
  }

  // The analytics pane on a recomputed bar or line chart (charts/pane.py apply_category).
  function applyPane(opt, b, model, table, ctx) {
    var pane = b.pane;
    var series = opt.series.filter(function (s) {
      return (s.type === "bar" || s.type === "line") && String(s.name).indexOf("Other (") !== 0;
    });
    if (!series.length) return opt;
    var cat = b.horizontal ? opt.yAxis : opt.xAxis;
    var nReal = series[0].data.length;
    var partial = !!pane.partial_key && model.keys[nReal - 1] === pane.partial_key;
    var value = function (d) { return d && typeof d === "object" ? d.value : d; };
    var added = false;
    var fmt = opt.tooltip && opt.tooltip.formatter && opt.tooltip.formatter.$tooltip;
    if (pane.forecast && b.time) {
      var horizon = pane.forecast;
      var nFit = nReal - (partial ? 1 : 0);
      var after = (b.periods || []).concat(b.periods_after || []);
      var last = model.keys[nReal - 1];
      var at = after.indexOf(last);
      var extraKeys = at >= 0 ? after.slice(at + 1, at + 1 + horizon - (partial ? 1 : 0)) : [];
      var drawn = [];
      var failed = null;
      series.slice(0, 6).forEach(function (s) {
        if (failed) return;
        var fc = forecast(s.data.slice(0, nFit).map(value), horizon, pane.season || null);
        if (fc.error) failed = fc.error;
        else drawn.push([s, fc]);
      });
      if (failed) {
        ctx.paneNote = "not enough data for a forecast: " + failed;
      } else if (drawn.length && extraKeys.length === horizon - (partial ? 1 : 0)) {
        var style = /\|(month|day)$/.test(b.dims[0]) && cat.data.length > 8 ? "compact" : "full";
        var labels = table.labels[b.dims[0]] || { full: {}, compact: {} };
        extraKeys.forEach(function (k) { cat.data.push(labels[style][k] || k); });
        var total = cat.data.length;
        opt.series.forEach(function (s) {
          while (s.data.length < total) s.data.push(null);
        });
        var single = drawn.length === 1;
        var bands = {};
        drawn.forEach(function (pair) {
          var s = pair[0];
          var fc = pair[1];
          var color = (s.itemStyle && s.itemStyle.color) || "#4e79a7";
          var name = single ? "Estimate" : s.name + " (estimate)";
          var data = [];
          var low = [];
          var high = [];
          for (var i = 0; i < total; i++) {
            data.push(null);
            low.push(null);
            high.push(null);
          }
          data[nFit - 1] = value(s.data[nFit - 1]);
          fc.values.forEach(function (v, h) {
            data[nFit + h] = v;
            low[nFit + h] = fc.lower[h];
            high[nFit + h] = fc.upper[h];
          });
          opt.series.push(dashed(name, data, color, 2));
          bands[name] = { low: low, high: high };
          if (single) {
            opt.series.push({ type: "line", name: HELPER + "estimate-low", data: low, stack: "ts-band", symbol: "none", lineStyle: { opacity: 0 }, silent: true, z: 1 });
            opt.series.push({
              type: "line", name: HELPER + "estimate-range", stack: "ts-band", symbol: "none", lineStyle: { opacity: 0 }, silent: true, z: 1,
              data: low.map(function (lo, i) { return lo === null ? null : high[i] - lo; }),
              areaStyle: { color: color, opacity: 0.14 },
            });
          }
        });
        if (fmt) {
          fmt.skip = [HELPER + "estimate-low", HELPER + "estimate-range"];
          fmt.bands = bands;
          fmt.series_fmt = fmt.series_fmt || {};
          Object.keys(bands).forEach(function (n) { fmt.series_fmt[n] = fmt.fmt; });
        }
        added = true;
      }
    }
    if (pane.trend) {
      series.slice(0, 6).forEach(function (s) {
        var ys = s.data.slice(0, nReal).map(value);
        var fit = linearTrend(ys.slice(0, nReal - (partial ? 1 : 0)));
        if (!fit) return;
        var line = [];
        for (var i = 0; i < nReal; i++) line.push(fit.intercept + fit.slope * i);
        while (line.length < cat.data.length) line.push(null);
        var name = series.length === 1 ? "Trend" : s.name + " trend";
        opt.series.push(dashed(name, line, (s.itemStyle && s.itemStyle.color) || "#4e79a7", 1.5));
        added = true;
      });
    }
    if (pane.outliers) {
      series.slice(0, 6).forEach(function (s) {
        var n = nReal - (partial ? 1 : 0);
        var ys = s.data.slice(0, n).map(value);
        var fit = linearTrend(ys);
        if (!fit) return;
        var resid = ys.map(function (y, i) { return y === null ? null : y - (fit.intercept + fit.slope * i); });
        var mask = outlierMask(resid, 1.5);
        var points = [];
        mask.forEach(function (m, i) { if (m) points.push({ coord: [i, ys[i]], value: ys[i] }); });
        if (points.length) {
          s.markPoint = { symbol: "circle", symbolSize: 13, silent: true, data: points, label: { show: false },
                          itemStyle: { color: "transparent", borderColor: "#d62728", borderWidth: 2 } };
        }
      });
    }
    var refs = pane.ref || [];
    var shown = [];
    series.forEach(function (s) { s.data.slice(0, nReal).forEach(function (d) { shown.push(value(d)); }); });
    var axis = b.horizontal ? "xAxis" : "yAxis";
    var valueAxis = opt[axis] && !Array.isArray(opt[axis]) ? opt[axis] : {};
    var axisFmt = (valueAxis.axisLabel && valueAxis.axisLabel.formatter && valueAxis.axisLabel.formatter.$fmt) || { unit: "number" };
    var lines = [];
    refs.forEach(function (ref) {
      var v = refValue(shown, ref);
      if (v === null) return;
      var label = refLabel(ref);
      var item = { name: label, label: { formatter: { $label: Object.assign({}, axisFmt, { style: "compact" }), prefix: label + " " }, position: "insideEndTop", color: ctx.textSecondary } };
      item[axis] = v;
      lines.push(item);
    });
    if (lines.length) series[0].markLine = { symbol: "none", silent: true, data: lines, lineStyle: { type: "dashed", color: ctx.textSecondary, width: 1 } };
    if (pane.band) {
      var lo = refValue(shown, pane.band[0]);
      var hi = refValue(shown, pane.band[1]);
      if (lo !== null && hi !== null) {
        var from = {};
        var to = {};
        from[axis] = Math.min(lo, hi);
        to[axis] = Math.max(lo, hi);
        series[0].markArea = { silent: true, itemStyle: { color: ctx.accent, opacity: 0.08 }, data: [[from, to]] };
      }
    }
    if (added) {
      opt.legend = opt.legend || { top: 0, left: 0, type: "scroll", icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: ctx.textSecondary } };
      opt.legend.data = opt.series.map(function (s) { return s.name; }).filter(function (n, i, all) {
        return String(n).charAt(0) !== HELPER && all.indexOf(n) === i;
      });
      opt.grid = opt.grid || {};
      opt.grid.top = Math.max(40, opt.grid.top || 0);
    }
    return opt;
  }

  function dashed(name, data, color, width) {
    return { type: "line", name: name, data: data, smooth: false, showSymbol: false, symbol: "none",
             lineStyle: { type: "dashed", width: width, color: color }, itemStyle: { color: color },
             emphasis: { disabled: true }, z: 3 };
  }

  // ------------------------------------------------------------- insights after filtering
  // A port of the rules in tabsight/insight.py that can be recomputed from the shared table:
  // change on the previous period, peak and low, trend, biggest contributor, concentration
  // and negative segments. Seasonality and outliers need every row, so they keep the
  // all-data version and say so.

  function fill(template, params) {
    return template.replace(/\{([a-z_]{1,30})\}/g, function (m, k) {
      return params.hasOwnProperty(k) ? String(params[k]) : m;
    });
  }

  function sentence(cfg, key, params) {
    var out = fill(cfg.templates[key], params);
    return out.charAt(0).toUpperCase() + out.slice(1);
  }

  function computeInsights(payload, table, filters) {
    var cfg = payload.live_insights;
    var tsj = root.tabsight;
    var loc = payload.locales;
    var th = cfg.thresholds;
    var rows = matching(table, filters, null);
    var minGroup = payload.min_group_size;
    var found = [];
    var pct = function (share, sign) {
      var d = Math.abs(share) < 0.1 ? 1 : 0;
      return tsj.formatNumber(share, sign ? cfg.pct_sign[d] : cfg.pct[d], loc);
    };
    var name = function (s) { return String(s).replace(/_/g, " "); };
    var measureWord = function (m) {
      return m.agg === "mean" ? "average " + name(m.label) : name(m.label);
    };
    var delta = function (cur, prev, m) {
      if (m.unit === "percent" || m.unit === "pp") {
        var out = tsj.formatNumber(cur - prev, m.pp, loc);
        return /^[-+−]/.test(out) ? out : "+" + out;
      }
      return pct(cur / prev - 1, true);
    };
    cfg.measures.forEach(function (m) {
      var what = measureWord(m);
      if (cfg.date) {
        var col = cfg.date.col;
        var grain = cfg.date.grain;
        var cells = group(table, rows, [col], [m]);
        var keys = cells.order.map(function (id) { return cells.groups[id].keys[0]; }).filter(function (k) { return k !== null; }).sort();
        if (cfg.date.partial_key && keys.length > 1 && keys[keys.length - 1] === cfg.date.partial_key) keys.pop();
        if (keys.length) {
          var lo = cfg.date.periods.indexOf(keys[0]);
          var hi = cfg.date.periods.indexOf(keys[keys.length - 1]);
          if (lo >= 0 && hi >= lo) keys = cfg.date.periods.slice(lo, hi + 1);
        }
        var values = keys.map(function (k) {
          var g = cells.groups[JSON.stringify([k])];
          if (!g) return m.agg === "sum" ? 0 : null;
          return finish(g.parts, m, minGroup);
        });
        var labels = keys.map(function (k) { return (table.labels[col] || { full: {} }).full[k] || k; });
        var finite = values.filter(function (v) { return v !== null; });
        if (values.length >= th.min_periods && finite.length) {
          var i = 0;
          var j = 0;
          values.forEach(function (v, k) {
            if (v !== null && (values[i] === null || v > values[i])) i = k;
            if (v !== null && (values[j] === null || v < values[j])) j = k;
          });
          var change = "";
          if (i > 0 && values[i - 1] !== null && values[i - 1] > 0) {
            change = fill(cfg.templates.ins_vs, { pct: delta(values[i], values[i - 1], m), period: labels[i - 1] });
          }
          found.push({ kind: "peak", score: 70, fields: [m.label, col], text: sentence(cfg, "ins_peak",
            { measure: what, period: labels[i], value: tsj.formatNumber(values[i], m.compact, loc), change: change }) });
          if (j !== i && values.length >= 6) {
            found.push({ kind: "low", score: 45, fields: [m.label, col], text: sentence(cfg, "ins_low",
              { measure: what, period: labels[j], value: tsj.formatNumber(values[j], m.compact, loc) }) });
          }
          var fit = linearTrend(values);
          var mean = finite.reduce(function (a, v) { return a + v; }, 0) / finite.length;
          if (fit && mean > 0 && fit.r2 >= th.trend_r2) {
            var per = fit.slope / mean;
            if (Math.abs(per) >= th.trend_min_change) {
              found.push({ kind: "trend", score: 60 + 30 * fit.r2, fields: [m.label, col], text: sentence(cfg,
                per > 0 ? "ins_trend_up" : "ins_trend_down", { grain_adj: cfg.date.adj, measure: what, pct: pct(Math.abs(per)),
                grain: grain, start: labels[0], end: labels[labels.length - 1] }) });
            }
          }
        }
      }
      if (cfg.change) {
        var only = function (which) {
          var set = {};
          set[which] = 1;
          var f = {};
          for (var k in filters) f[k] = filters[k];
          f[cfg.change.window] = { type: "in", set: set, mode: "filter" };
          var rs = matching(table, f, null);
          if (!rs.length) return null;
          var parts = newParts();
          rs.forEach(function (r) { addRow(table, parts, r, [m]); });
          return finish(parts, m, minGroup);
        };
        var cur = only("cur");
        var prev = only("prev");
        if (cur !== null && prev !== null && prev !== 0) {
          var d = cur - prev;
          var key = d > 0 ? "ins_change_up" : d < 0 ? "ins_change_down" : "ins_change_flat";
          var size = delta(cur, prev, m).replace(/^[-+−]/, "");
          found.push({ kind: "change", score: 90 + Math.min(Math.abs(d / Math.abs(prev)) * 100, 50), fields: [m.label, cfg.change.window],
            text: sentence(cfg, key, { measure: what, pct: size, current: cfg.change.current, previous: cfg.change.previous }) });
        }
      }
      cfg.dims.forEach(function (dim) {
        var cells = group(table, rows, [dim.col], [m]);
        var list = cells.order.map(function (id) {
          var g = cells.groups[id];
          return { name: g.keys[0] === null ? payload.unknown : String(g.keys[0]), value: finish(g.parts, m, minGroup) };
        }).filter(function (r) { return r.value !== null; });
        list.sort(function (a, c) { return c.value - a.value || naturalCompare(a.name, c.name); });
        if (list.length < 2) return;
        var many = dim.title;
        var total = list.reduce(function (a, r) { return a + r.value; }, 0);
        var additive = m.agg === "sum" || m.agg === "count";
        if (additive && total > 0 && list.every(function (r) { return r.value >= 0; })) {
          var share = list[0].value / total;
          if (share >= th.contributor && list.length >= 3) {
            found.push({ kind: "contributor", score: 50 + 30 * share, fields: [m.label, dim.col], name: list[0].name,
              text: sentence(cfg, "ins_contributor", { name: list[0].name, pct: pct(share), measure: what }) });
          }
          var top3 = (list[0].value + list[1].value + (list[2] ? list[2].value : 0)) / total;
          if (list.length >= th.concentration_min_values && top3 >= th.concentration) {
            var names = list.slice(0, 3).map(function (r) { return r.name; });
            found.push({ kind: "concentration", score: 55 + 30 * top3, fields: [m.label, dim.col], name: names.join("|"),
              text: sentence(cfg, "ins_concentration", { n: 3, dim: many, pct: pct(top3), measure: what,
                names: names.slice(0, -1).join(", ") + " and " + names[names.length - 1] }) });
          }
        }
        var negative = list.filter(function (r) { return r.value < 0; });
        if (negative.length && negative.length < list.length) {
          var shown = negative.slice().sort(function (a, c) { return a.value - c.value; }).slice(0, 3).map(function (r) { return r.name; });
          var more = negative.length - shown.length;
          var named = more ? shown.join(", ") + fill(cfg.templates.ins_and_more, { n: more })
            : shown.length === 1 ? shown[0] : shown.slice(0, -1).join(", ") + " and " + shown[shown.length - 1];
          found.push({ kind: "negative", score: 75, fields: [m.label, dim.col], name: negative.map(function (r) { return r.name; }).join("|"),
            text: sentence(cfg, "ins_negative", { k: negative.length, n: list.length, dim: many, measure: what, names: named }) });
        }
      });
    });
    found = found.concat(cfg.kept.map(function (k) { return { kind: k.kind, score: k.kind === "seasonality" ? 65 : 40, fields: k.fields, text: k.text, allData: true }; }));
    found.sort(function (a, c) { return c.score - a.score; });
    var kept = [];
    var seen = dict();
    var perKind = dict();
    found.forEach(function (item) {
      var ident = JSON.stringify([item.kind, item.fields.slice(1), item.name || ""]);
      if ((item.kind === "contributor" || item.kind === "concentration" || item.kind === "negative") && seen[ident]) return;
      if ((perKind[item.kind] || 0) >= th.max_per_kind) return;
      seen[ident] = 1;
      perKind[item.kind] = (perKind[item.kind] || 0) + 1;
      kept.push(item);
    });
    return kept.slice(0, cfg.max_items);
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
      textSecondary: (fig.theme || payload.theme).text_secondary,
      accent: (fig.theme || payload.theme).accent,
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
    var special = {
      funnel: funnelTile, pareto: paretoTile, waterfall: waterfallTile, heatmap: heatmapTile, tree: treeTile,
      sankey: sankeyTile, calendar: calendarTile, histogram: histogramTile, points: pointsTile,
      points_map: pointsMapTile, flows: flowsTile, box: boxTile, numeric_lines: numericLinesTile,
    }[b.shape];
    if (b.shape === "gauge") {
      fig.option = gaugeTile(fig, b, table, rows, ctx);
      return { figure: fig, keys: [] };
    }
    if (b.shape === "bullet" && !b.dims.length) {
      fig.option = bulletValue(fig, b, table, rows, ctx);
      return { figure: fig, keys: [] };
    }
    if (b.shape === "bullet") {
      var bt = bulletTile(fig, b, table, rows, ctx);
      fig.option = bt.option;
      return { figure: fig, keys: bt.keys, labels: bt.labels, series: bt.model.series };
    }
    if (special) {
      var st = special(fig, b, table, rows, ctx, payload);
      fig.option = st.option;
      return { figure: fig, keys: st.keys, other: st.other || [], labels: st.labels, series: st.model && st.model.series };
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
    if (fig.kind === "lollipop") fig.option = lollipop(fig.option, tile.figure.option, b);
    if (b.pane && fig.kind !== "donut") fig.option = applyPane(fig.option, b, model, table, ctx);
    return { figure: fig, keys: model.keys, other: model.other, labels: labels, series: model.series, note: ctx.paneNote };
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
        g.set = dict();
        f.values.forEach(function (v) {
          g.set[v === null ? "\u0000null" : v] = 1;
        });
      }
      out[col] = g;
    }
    return out;
  }

  // ------------------------------------------------------------- the page

  var LONG_PRESS_MS = 450; // touch: hold this long to filter; a shorter tap shows the tooltip

  function el(tag, cls, text) {
    var e = root.document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  // One tile as the recompute code sees it: the chosen view, in the chosen theme.
  function flatTile(t, themeName) {
    var view = t.tile.views[t.view];
    var side = view.themes[themeName] || view.themes[Object.keys(view.themes)[0]];
    return { id: t.tile.id, action: t.tile.action, figure: side.figure, binding: side.binding || null,
             static: side.static || null, kind: view.kind };  // prettier-ignore
  }

  function mount(container, payload) {
    var doc = root.document;
    var tsj = root.tabsight;
    var tables = { main: new Table(payload.data) };
    Object.keys(payload.datasets || {}).forEach(function (name) {
      tables[name] = new Table(payload.datasets[name]);
    });
    var table = tables.main;
    // Server mode: the page holds no rows; it posts its filters to this address and draws
    // the small tables (or finished charts) that come back. See tabsight/server.py.
    var server = payload.server && typeof root.fetch === "function" ? payload.server.url : null;
    var state = {}; // col -> {type, values|lo,hi, source, mode}
    var tiles = [];
    var themes = payload.themes || [payload.theme.name];
    var themeName = payload.theme.name;
    if (!payload.theme_explicit && themes.indexOf("dark") >= 0 && root.matchMedia && root.matchMedia("(prefers-color-scheme: dark)").matches) {
      themeName = "dark";
    }
    tsj.registerMaps(payload.maps || []);

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

    function label(col, key, tbl) {
      tbl = tbl || table;
      if (key === null) return payload.unknown;
      if (key === OTHER_KEY) return payload.other;
      var l = tbl.labels[col];
      return l ? l.full[key] || key : String(key);
    }
    function title(col, tbl) {
      tbl = tbl || table;
      var meta = tbl.meta[col];
      return (meta && meta.title) || String(col).split("|")[0].replace(/_/g, " ");
    }

    // ---- theme
    var showToggle = null;
    function applyTheme() {
      themes.forEach(function (name) {
        var css = doc.getElementById("ts-css-" + name);
        if (css) css.media = name === themeName ? "all" : "not all";
      });
      doc.documentElement.setAttribute("data-theme", themeName);
      if (typeof showToggle === "function") showToggle();
    }
    applyTheme();

    // ---- filter bar
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
            var t2 = lo;
            lo = hi;
            hi = t2;
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
          cb.addEventListener("change", function () {
            var chosen = boxes.filter(function (x) { return x.cb.checked; }).map(function (x) { return x.key; });
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
    if (themes.length > 1 && payload.theme_toggle !== false) {
      var toggle = el("button", "ts-theme-toggle");
      toggle.type = "button";
      showToggle = function () {
        toggle.textContent = themeName === "dark" ? "☀ Light" : "☾ Dark";
        toggle.setAttribute("aria-label", themeName === "dark" ? "Switch to the light theme" : "Switch to the dark theme");
      };
      showToggle();
      toggle.addEventListener("click", function () {
        themeName = themeName === "dark" ? "light" : "dark";
        applyTheme();
        showToggle();
        tiles.forEach(function (t) { if (t.drawn) render(t); });
      });
      bar.appendChild(toggle);
    }

    function syncControls() {
      for (var col in controls) {
        var c = controls[col];
        var s = state[col];
        if (c.boxes) {
          var set = dict();
          if (s && s.type === "in" && !s.source) {
            s.values.forEach(function (v) { set[v === null ? "\u0000null" : v] = 1; });
          }
          c.boxes.forEach(function (x) { x.cb.checked = has(set, x.key === null ? "\u0000null" : x.key); });
          c.summary.textContent = c.filter.title + (s && !s.source && s.values ? ": " + s.values.length + " selected" : ": all");
        } else {
          var vals = c.filter.values;
          c.from.value = String(s && s.type === "range" && !s.source ? Math.max(0, vals.indexOf(s.lo)) : 0);
          c.to.value = String(s && s.type === "range" && !s.source ? Math.max(0, vals.indexOf(s.hi)) : vals.length - 1);
        }
      }
    }

    function chipTable(col) {
      if (table.dims[col]) return table;
      for (var n in tables) if (tables[n].dims[col]) return tables[n];
      return table;
    }

    function drawChips() {
      chips.textContent = "";
      var any = false;
      Object.keys(state).forEach(function (col) {
        var s = state[col];
        var tbl = chipTable(col);
        any = true;
        var text =
          s.type === "range"
            ? title(col, tbl) + ": " + label(col, s.lo, tbl) + " – " + label(col, s.hi, tbl)
            : title(col, tbl) + ": " + s.values.map(function (v) { return label(col, v, tbl); }).join(", ");
        if (s.mode === "highlight") text += " (highlight)";
        var chip = el("span", "ts-chip");
        chip.appendChild(el("span", null, text.length > 120 ? text.slice(0, 117) + "…" : text));
        var x = el("button", "ts-chip__x", "×");
        x.type = "button";
        x.setAttribute("aria-label", "Remove filter " + title(col, tbl));
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

    // ---- tiles
    payload.tiles.forEach(function (tile) {
      var t = { tile: tile, view: 0, drill: [], chart: null, keys: [], other: [], drawn: false, result: null, focus: null, ctrl: false };
      var first = flatTile(t, themeName).figure;
      var box = el("section", "ts-tile ts-dash-tile");
      box.style.gridColumn = "span " + Math.max(1, Math.min(12, tile.w || 6));
      var head = el("header", "ts-tile__head");
      t.titleEl = el("h2", "ts-tile__title", first.title);
      head.appendChild(t.titleEl);
      var tools = el("div", "ts-tile__tools");
      var choices = tile.views.map(function (v, i) { return [v, i]; }).filter(function (p) { return !p[0].drill; });
      if (choices.length > 1) {
        var pickKind = el("select", "ts-tile__kind");
        pickKind.setAttribute("aria-label", "Chart type");
        choices.forEach(function (p) {
          var o = el("option", null, p[0].label);
          o.value = String(p[1]);
          pickKind.appendChild(o);
        });
        pickKind.addEventListener("change", function () {
          t.view = parseInt(pickKind.value, 10);
          t.drill = [];
          render(t);
        });
        t.pickKind = pickKind;
        tools.appendChild(pickKind);
      }
      var png = el("button", "ts-tile__csv", "PNG");
      png.type = "button";
      png.setAttribute("aria-label", "Save " + first.title + " as PNG");
      png.addEventListener("click", function () { downloadPng(t); });
      t.png = png;
      tools.appendChild(png);
      var csv = el("button", "ts-tile__csv", payload.words.csv);
      csv.type = "button";
      csv.addEventListener("click", function () { downloadCsv(t); });
      tools.appendChild(csv);
      head.appendChild(tools);
      if (first.subtitle) head.appendChild(el("p", "ts-tile__subtitle", first.subtitle));
      box.appendChild(head);
      var body = el("div", "ts-tile__body");
      t.crumbs = el("nav", "ts-crumbs");
      t.crumbs.setAttribute("aria-label", "Drill-down");
      body.appendChild(t.crumbs);
      t.target = el("div", "ts-chart");
      t.target.setAttribute("role", "img");
      t.target.setAttribute("aria-label", first.title);
      t.target.addEventListener("pointerdown", function (ev) {
        t.ctrl = ev.ctrlKey || ev.metaKey;
        // On a touch screen a tap shows the tooltip; pressing and holding filters.
        t.touch = ev.pointerType === "touch";
        t.downAt = Date.now();
        clearTimeout(t.holdTimer);
        if (t.touch) {
          t.holdTimer = setTimeout(function () {
            box.classList.add("ts-dash-tile--hold");
            if (root.navigator && typeof root.navigator.vibrate === "function") root.navigator.vibrate(12);
          }, LONG_PRESS_MS);
        }
      }, true);
      var release = function () {
        clearTimeout(t.holdTimer);
        setTimeout(function () { box.classList.remove("ts-dash-tile--hold"); }, 150);
      };
      t.target.addEventListener("pointerup", release, true);
      t.target.addEventListener("pointercancel", release, true);
      if (first.kind !== "kpi" && first.kind !== "table") t.target.style.height = first.height + "px"; // no jump when drawn
      body.appendChild(t.target);
      t.notes = el("div", "ts-tile__notes");
      body.appendChild(t.notes);
      t.status = el("p", "ts-tile__status");
      body.appendChild(t.status);
      box.appendChild(body);
      grid.appendChild(box);
      t.box = box;
      tiles.push(t);
    });

    function tileTable(t) {
      return tables[t.tile.data || "main"] || table;
    }

    // Filters for one tile: drill steps apply to it alone; filters on fields its data lacks are skipped.
    function tileFilters(t) {
      var tbl = tileTable(t);
      var out = {};
      var skipped = [];
      Object.keys(state).forEach(function (col) {
        if (tbl.dims[col]) out[col] = state[col];
        else skipped.push(title(col, chipTable(col)));
      });
      t.drill.forEach(function (d) {
        out[d.col] = { type: "in", values: [d.key], source: null, mode: "filter" };
      });
      return { filters: out, skipped: skipped };
    }

    function drillViews(t) {
      var out = [];
      t.tile.views.forEach(function (v, i) { if (v.drill) out.push(i); });
      return out;
    }

    function showCrumbs(t) {
      t.crumbs.textContent = "";
      if (!t.drill.length) return;
      var home = el("button", "ts-crumb", "All");
      home.type = "button";
      home.addEventListener("click", function () {
        t.drill = [];
        t.view = 0;
        render(t);
      });
      t.crumbs.appendChild(home);
      t.drill.forEach(function (d, i) {
        t.crumbs.appendChild(el("span", "ts-crumb__sep", "›"));
        var last = i === t.drill.length - 1;
        var c = el(last ? "span" : "button", "ts-crumb", d.label);
        if (!last) {
          c.type = "button";
          c.addEventListener("click", function () {
            t.drill = t.drill.slice(0, i + 1);
            t.view = drillViews(t)[i];
            render(t);
          });
        }
        t.crumbs.appendChild(c);
      });
    }

    function showNotes(t, flat, filtered, result, skipped) {
      t.notes.textContent = "";
      if (!filtered) {
        (flat.figure.notes || []).forEach(function (n) { t.notes.appendChild(el("p", "ts-note", n)); });
      } else {
        if (t.other && t.other.length) t.notes.appendChild(el("p", "ts-note", "Other groups " + t.other.length + " values (filtered)"));
        if (result && result.note) t.notes.appendChild(el("p", "ts-note", result.note));
      }
      var status = [];
      if (flat.static && !server && Object.keys(state).length) status.push("Not affected by filters: " + flat.static);
      else if (filtered && flat.binding) status.push(payload.words.current);
      skipped.forEach(function (f) { status.push(payload.words.not_affected.replace("{field}", f)); });
      t.status.textContent = status.join(" · ");
    }

    // ---- server mode: one request for every tile that needs new numbers
    var queue = {};
    var queued = false;
    var insightTable = null;
    var insightKey = null;
    var wantInsights = false;

    function remoteKey(t) {
      var flat = flatTile(t, themeName);
      return JSON.stringify([state, t.view, t.drill.map(function (d) { return d.col; }), flat.static ? themeName : ""]);
    }

    function ask(t) {
      if (t) queue[t.tile.id] = t;
      if (queued) return;
      queued = true;
      setTimeout(flush, 0);
    }

    function flush() {
      queued = false;
      var list = Object.keys(queue).map(function (id) { return queue[id]; });
      queue = {};
      var keys = list.map(remoteKey);
      var stateKey = JSON.stringify(state);
      var withInsights = wantInsights;
      wantInsights = false;
      if (!list.length && !withInsights) return;
      list.forEach(function (t) { t.box.setAttribute("aria-busy", "true"); });
      var body = {
        state: state,
        insights: withInsights,
        tiles: list.map(function (t) {
          return { id: t.tile.id, view: t.view, drill: t.drill.map(function (d) { return d.col; }), theme: themeName };
        }),
      };
      root
        .fetch(server, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                         credentials: "same-origin", cache: "no-store" })  // prettier-ignore
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (reply) {
          list.forEach(function (t, i) {
            t.box.removeAttribute("aria-busy");
            if (t.pending !== keys[i]) return; // the viewer has moved on; a newer answer is coming
            t.remote = (reply.tiles || {})[t.tile.id] || { empty: true };
            t.remoteKey = keys[i];
            t.pending = null;
            render(t);
          });
          if (withInsights && reply.insights && JSON.stringify(state) === stateKey) {
            insightTable = new Table(reply.insights);
            insightKey = stateKey;
            showInsights();
          }
        })
        .catch(function () {
          list.forEach(function (t) {
            t.box.removeAttribute("aria-busy");
            t.pending = null;
            t.status.textContent = "Could not reach the server for new numbers.";
          });
        });
    }

    function render(t) {
      var flat = flatTile(t, themeName);
      var tbl = tileTable(t);
      var tf = tileFilters(t);
      var filtered = Object.keys(tf.filters).length > 0;
      var fig = flat.figure;
      var result = null;
      t.titleEl.textContent = fig.title;
      t.target.setAttribute("aria-label", fig.title);
      if (t.pickKind) t.pickKind.value = String(t.drill.length ? 0 : t.view);
      var answer = null;
      if (server) {
        var want = remoteKey(t);
        if (t.remoteKey !== want) {
          if (t.pending !== want) {
            t.pending = want;
            ask(t);
          }
          if (t.chart || t.target.childNodes.length) return; // keep the last drawing until the answer comes
        } else {
          answer = t.remote;
        }
      }
      if (answer && answer.empty) {
        if (t.chart) {
          t.chart.dispose();
          t.chart = null;
        }
        t.target.style.height = "";
        t.target.textContent = "";
        t.target.appendChild(el("p", "ts-note", payload.words.no_data));
        t.keys = [];
        showCrumbs(t);
        t.notes.textContent = "";
        t.status.textContent = "";
        return;
      }
      if (answer && answer.figure) {
        fig = answer.figure;
        flat = { id: flat.id, action: flat.action, figure: fig, binding: null, static: null, kind: flat.kind };
      }
      if (flat.binding && (!server || answer)) {
        result = compute(payload, server ? new Table(answer.table) : tbl, flat, prepare(tf.filters));
        t.keys = result.keys;
        t.other = result.other || [];
        t.result = result;
        if (filtered) fig = result.figure; // unfiltered, the tile shows exactly what Python drew
      }
      showCrumbs(t);
      showNotes(t, flat, filtered && !!flat.binding, result, tf.skipped);
      var dom = fig.kind === "kpi" || fig.kind === "table";
      t.png.hidden = dom;
      if (dom) {
        if (t.chart) {
          t.chart.dispose();
          t.chart = null;
        }
        t.target.style.height = "";
        tsj.render(t.target, fig);
        if (fig.kind === "table" && flat.binding) bindTable(t);
        return;
      }
      t.target.style.height = fig.height + "px";
      var raw = clone(fig.option);
      var multi = (raw.series || []).filter(function (s) { return String(s.name || "").charAt(0) !== HELPER; }).length > 1;
      if (multi && raw.legend) {
        // A legend click highlights its series; that needs series to fade the others.
        raw.series.forEach(function (s) {
          if (s.type === "bar" || s.type === "line" || s.type === "scatter") s.emphasis = Object.assign({ focus: "series" }, s.emphasis || {});
        });
      }
      var brushable = flat.binding && flat.binding.time && (fig.kind === "line" || fig.kind === "area" || fig.kind === "multi_line" || fig.kind === "stacked_area");
      if (brushable) {
        raw.brush = { xAxisIndex: 0, brushType: "lineX", brushMode: "single", throttleType: "debounce", throttleDelay: 250,
                      brushStyle: { color: "rgba(78,121,167,0.12)", borderColor: "rgba(78,121,167,0.6)" }, outOfBrush: { colorAlpha: 0.35 } };  // prettier-ignore
        raw.toolbox = { show: false, feature: { brush: { type: ["lineX"] } } };
      }
      var option = tsj.hydrate(raw, fig.locales || payload.locales);
      var aspects = tsj.fitAspects(option);
      if (!t.chart) {
        t.target.textContent = "";
        t.chart = root.echarts.init(t.target, null, { renderer: "canvas" });
        t.chart.on("click", function (p) { onClick(t, p); });
        t.chart.on("dblclick", function (p) { onDrill(t, p); });
        t.chart.on("legendselectchanged", function (e) { onLegend(t, e); });
        t.chart.on("brushEnd", function (e) { onBrush(t, e); });
        if (typeof root.ResizeObserver === "function") {
          new root.ResizeObserver(function () {
            if (!t.chart) return;
            t.chart.resize();
            tsj.fitMaps(t.chart, t.aspects);
          }).observe(t.target);
        }
      }
      t.aspects = aspects;
      t.focus = null;
      t.chart.setOption(option, { notMerge: true });
      tsj.fitMaps(t.chart, aspects);
      if (brushable) {
        t.chart.dispatchAction({ type: "takeGlobalCursor", key: "brush", brushOption: { brushType: "lineX", brushMode: "single" } });
        var own = state[flat.binding.click];
        if (own && own.type === "range" && own.source === t.tile.id) {
          var a = t.keys.indexOf(own.lo);
          var z = t.keys.indexOf(own.hi);
          if (a >= 0 && z >= 0) t.chart.dispatchAction({ type: "brush", areas: [{ brushType: "lineX", xAxisIndex: 0, coordRange: [a, z] }] });
        }
      }
    }

    function onLegend(t, e) {
      if (t.ctrl) return; // Ctrl + click hides the series, as ECharts does
      t.chart.dispatchAction({ type: "legendSelect", name: e.name });
      t.chart.dispatchAction({ type: "downplay" });
      if (t.focus === e.name) {
        t.focus = null;
      } else {
        t.chart.dispatchAction({ type: "highlight", seriesName: e.name });
        t.focus = e.name;
      }
    }

    function onBrush(t, e) {
      var flat = flatTile(t, themeName);
      var b = flat.binding;
      if (!b || !e.areas) return;
      var col = b.click;
      if (!e.areas.length) {
        if (state[col] && state[col].source === t.tile.id) {
          delete state[col];
          update();
        }
        return;
      }
      var range = e.areas[0].coordRange || [];
      var a = Math.max(0, Math.round(range[0]));
      var z = Math.min(t.keys.length - 1, Math.round(range[1]));
      var lo = t.keys[a];
      var hi = t.keys[z];
      if (lo === undefined || hi === undefined || lo === OTHER_KEY || hi === OTHER_KEY) return;
      var cur = state[col];
      if (cur && cur.type === "range" && cur.lo === lo && cur.hi === hi) return;
      state[col] = { type: "range", lo: lo, hi: hi, source: t.tile.id, mode: "filter" };
      update();
    }

    function onDrill(t, p) {
      var flat = flatTile(t, themeName);
      var b = flat.binding;
      var steps = drillViews(t);
      var depth = t.drill.length;
      var atBase = t.view === 0 || (depth && t.view === steps[depth - 1]);
      if (!b || !atBase || depth >= steps.length || p.dataIndex === undefined) return;
      var key = t.keys[p.dataIndex];
      if (key === undefined || key === OTHER_KEY) return;
      if (state[b.click] && state[b.click].source === t.tile.id) delete state[b.click]; // the double click's clicks
      t.drill.push({ col: b.click, key: key, label: label(b.click, key, tileTable(t)) });
      t.view = steps[depth];
      update();
    }

    function bindTable(t) {
      var body = t.target.querySelector("tbody");
      if (!body) return;
      Array.prototype.forEach.call(body.querySelectorAll("tr"), function (tr, i) {
        tr.tabIndex = 0;
        tr.style.cursor = "pointer";
        var go = function (ev) { pick(t, t.keys[i], ev.ctrlKey || ev.metaKey || ev.shiftKey); };
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
      p = Object.assign({}, p, { name: tsj.plainName(p.name) }); // names come back as ECharts drew them
      if (p.treePathInfo) p.treePathInfo = p.treePathInfo.map(function (n) { return { name: tsj.plainName(n.name) }; });
      var b = flatTile(t, themeName).binding;
      if (!b || !b.click || t.tile.action === "none") return;
      if (t.touch && Date.now() - t.downAt < LONG_PRESS_MS) return; // a tap: just the tooltip
      var ev = p.event && p.event.event ? p.event.event : {};
      var add = !!(ev.ctrlKey || ev.metaKey || ev.shiftKey);
      if (b.shape === "geo") {
        var raws = [];
        for (var raw in b.shapes) if (b.shapes[raw] === p.name) raws.push(raw);
        if (raws.length) pickMany(t, raws, add);
        return;
      }
      if (p.componentType !== "series") return;
      if (b.shape === "tree") {
        var path = p.treePathInfo || [];
        if (path.length > 1) pick(t, path[1].name === payload.unknown ? null : path[1].name, add);
        return;
      }
      if (b.shape === "sankey") {
        if (p.dataType === "node" && String(p.name).indexOf("→ ") !== 0) pick(t, p.name, add);
        return;
      }
      if (b.shape === "points" || b.shape === "points_map") {
        var names = [];
        if (b.shape === "points") names = [p.name === payload.unknown ? null : p.name];
        else for (var raw2 in b.points) if (b.points[raw2][3] === p.name) names.push(raw2);
        if (names.length) pickMany(t, names, add);
        return;
      }
      if (b.shape === "calendar") {
        if (Array.isArray(p.value)) pick(t, p.value[0], add);
        return;
      }
      if (b.shape === "heatmap") {
        if (Array.isArray(p.value) && t.keys[p.value[0]] !== undefined) pick(t, t.keys[p.value[0]], add);
        return;
      }
      if (b.shape === "flows" || p.dataIndex === undefined) return;
      if (String(p.seriesName || "").charAt(0) === HELPER) return;
      var key = t.keys[p.dataIndex];
      if (key === undefined) return;
      if (key === OTHER_KEY) pickMany(t, t.other, add);
      else pick(t, key, add);
    }

    function pick(t, key, add) {
      pickMany(t, [key], add);
    }

    // Click semantics: a click filters to that value; clicking it again removes
    // the filter; Ctrl/Shift + click adds or removes values.
    function pickMany(t, keys, add) {
      var col = flatTile(t, themeName).binding.click;
      var mode = t.tile.action === "highlight" ? "highlight" : "filter";
      var cur = state[col];
      var values = cur && cur.type === "in" && cur.source === t.tile.id ? cur.values.slice() : [];
      var same = values.length === keys.length && keys.every(function (k) { return values.indexOf(k) >= 0; });
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

    function save(name, href) {
      var a = el("a");
      a.href = href;
      a.download = name;
      doc.body.appendChild(a);
      a.click();
      setTimeout(function () {
        if (href.indexOf("blob:") === 0) root.URL.revokeObjectURL(href);
        a.remove();
      }, 0);
    }

    function fileName(t, ext) {
      return (flatTile(t, themeName).figure.title || "tile").replace(/[^\w\- ]+/g, "").slice(0, 60) + ext;
    }

    function downloadPng(t) {
      if (!t.chart) return;
      var bg = (payload.theme_css[themeName] || payload.theme).tile;
      save(fileName(t, ".png"), t.chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: bg }));
    }

    function downloadCsv(t) {
      var flat = flatTile(t, themeName);
      var b = flat.binding;
      var tbl = tileTable(t);
      var lines = [];
      var cell = function (v) {
        var s = v === null || v === undefined ? "" : String(v);
        if (payload.csv_safe !== false && typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
        return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      if (!b) {
        lines.push(cell("This tile is drawn from all the data; its numbers are in fig.to_dict() in Python."));
      } else if (t.result && t.result.rows) {
        lines.push(b.dims.map(function (c) { return title(c, tbl); }).concat(b.measures.map(function (m) { return m.label; })).map(cell).join(","));
        t.result.rows.forEach(function (row) {
          lines.push(row.keys.map(function (k, i) { return cell(label(b.dims[i], k, tbl)); }).concat(row.values.map(cell)).join(","));
        });
      } else if (t.result && t.result.series) {
        var head = [title(b.dims[0], tbl)];
        if (b.dims[1]) head.push(title(b.dims[1], tbl));
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
        var fig = t.result ? t.result.figure : flat.figure;
        lines.push(cell(fig.title));
        if (fig.kpi) lines.push(cell(fig.kpi.value_full || fig.kpi.value_text));
      }
      var blob = new root.Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
      save(fileName(t, ".csv"), root.URL.createObjectURL(blob));
    }

    // ---- insights panel
    var panel = doc.querySelector(".ts-dash-insights ul");
    var insightNote = doc.querySelector(".ts-dash-insights__scope");
    function showInsights() {
      if (!panel) return;
      var filtered = Object.keys(state).length > 0;
      if (server && filtered && payload.live_insights && insightKey !== JSON.stringify(state)) {
        wantInsights = true; // the answer calls showInsights again
        ask(null);
        return;
      }
      panel.textContent = "";
      var source = server ? insightTable : table;
      var items = filtered && payload.live_insights ? computeInsights(payload, source, prepare(state)) : null;
      if (!items) {
        (payload.insights || []).forEach(function (i) { panel.appendChild(el("li", null, i.text)); });
        if (insightNote) insightNote.textContent = filtered ? "These describe all the data, not the current filters." : payload.words.all_data;
        return;
      }
      if (!items.length) panel.appendChild(el("li", null, "No clear peak, trend, leader or loss for the current filters."));
      items.forEach(function (i) {
        var li = el("li", null, i.text + " ");
        li.appendChild(el("span", "ts-insights__scope", i.allData ? payload.words.all_data : payload.words.current));
        panel.appendChild(li);
      });
      if (insightNote) insightNote.textContent = "";
    }

    // ---- the address keeps the filters (#f=...), checked against the table's known values
    function saveHash() {
      try {
        var text = Object.keys(state).length ? "#f=" + encodeURIComponent(JSON.stringify(state)) : null;
        root.history.replaceState(null, "", text === null ? root.location.pathname + root.location.search : text);
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
      state = sanitize(raw, tables, payload);
    }

    var lazy = typeof root.IntersectionObserver === "function"
      ? new root.IntersectionObserver(function (entries) {
          entries.forEach(function (e) {
            if (!e.isIntersecting) return;
            var t = tiles.filter(function (x) { return x.target === e.target; })[0];
            if (t && !t.drawn) {
              t.drawn = true;
              render(t);
            }
          });
        }, { rootMargin: "200px" })
      : null;

    function update() {
      syncControls();
      drawChips();
      saveHash();
      showInsights();
      tiles.forEach(function (t) { if (t.drawn) render(t); });
    }

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
    root.addEventListener("hashchange", function () {
      var before = JSON.stringify(state);
      loadHash();
      if (JSON.stringify(state) !== before) update();
    });
    root.addEventListener("beforeprint", function () {
      tiles.forEach(function (t) {
        if (!t.drawn) {
          t.drawn = true;
          render(t);
        }
      });
    });

    loadHash();
    syncControls();
    drawChips();
    showInsights();
    tiles.forEach(function (t) {
      if (lazy) lazy.observe(t.target);
      else {
        t.drawn = true;
        render(t);
      }
    });
    var api = {
      state: function () { return clone(state); },
      set: function (s) {
        state = sanitize(s, tables, payload);
        update();
      },
      theme: function (name) {
        if (name && themes.indexOf(name) >= 0) {
          themeName = name;
          applyTheme();
          tiles.forEach(function (t) { if (t.drawn) render(t); });
        }
        return themeName;
      },
      view: function (i, v) {
        tiles[i].view = v;
        tiles[i].drill = [];
        render(tiles[i]);
      },
      drill: function (i, key) {
        onDrill(tiles[i], { dataIndex: tiles[i].keys.indexOf(key) });
      },
      tiles: tiles,
    };
    root.tabsightDashboard.page = api; // for scripts and tests on this page
    return api;
  }

  // Keep only filters on known columns with known values (address bar input is untrusted).
  function sanitize(raw, tables, payload) {
    var out = {};
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
    if (tables instanceof Table) tables = { main: tables };
    var sources = {};
    payload.tiles.forEach(function (t) { sources[t.id] = 1; });
    var known = function (col) {
      for (var n in tables) if (tables[n].dims[col]) return tables[n].known(col);
      return null;
    };
    for (var col in raw) {
      if (!Object.prototype.hasOwnProperty.call(raw, col) || col.indexOf("__") === 0) continue;
      var values = known(col);
      if (!values) continue;
      var f = raw[col];
      if (!f || typeof f !== "object") continue;
      var source = typeof f.source === "string" && sources[f.source] ? f.source : null;
      var mode = f.mode === "highlight" ? "highlight" : "filter";
      if (f.type === "range" && values.indexOf(f.lo) >= 0 && values.indexOf(f.hi) >= 0 && f.lo !== null && f.hi !== null) {
        out[col] = { type: "range", lo: f.lo, hi: f.hi, source: source, mode: "filter" };
      } else if (f.type === "in" && Array.isArray(f.values)) {
        var kept = f.values.filter(function (v) { return values.indexOf(v) >= 0; });
        if (kept.length) out[col] = { type: "in", values: kept, source: source, mode: mode };
      }
    }
    return out;
  }

  root.tabsightDashboard = {
    mount: mount,
    computeInsights: computeInsights,
    flatTile: flatTile,
    forecast: forecast,
    linearTrend: linearTrend,
    compute: compute,
    prepare: prepare,
    sanitize: sanitize,
    Table: Table,
    naturalCompare: naturalCompare,
    OTHER_KEY: OTHER_KEY,
  };
})(typeof window !== "undefined" ? window : globalThis);
