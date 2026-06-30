"use strict";
// ── Input/Change events: field editing, type switching ──

$("slist").addEventListener("change", function (e) {
  var el = e.target,
    cls = Array.from(el.classList),
    idx = parseInt(el.dataset.idx);
  if (isNaN(idx) || !steps[idx]) return;

  // Type selector
  if (cls.includes("ft")) {
    changeType(idx, el.value);
    return;
  }

  // Branch condition type / inner step type
  if (cls.includes("bdf") || cls.includes("bst")) {
    var j = parseInt(el.dataset.bidx),
      b = normalizeBranch(steps[idx].branches[j], j);
    if (cls.includes("bdf")) {
      if (el.value == "1") {
        delete b.if;
        b.default = true;
      } else {
        delete b.default;
        if (!b.if) b.if = "";
      }
    } else {
      setBranchStep(idx, j, el.value);
    }
    render();
    save();
    return;
  }

  // Parallel inner step type
  if (cls.includes("pst")) {
    var pj = parseInt(el.dataset.pidx);
    setParallelStep(idx, pj, el.value);
    render();
    save();
    return;
  }

  // Action batch JSON textarea
  if (cls.includes("fac")) {
    try {
      steps[idx].actions = JSON.parse(el.value);
    } catch (e) {}
    render();
    save();
    return;
  }

  // Branch JSON textarea
  if (cls.includes("fbr")) {
    try {
      steps[idx].branches = JSON.parse(el.value);
    } catch (e) {}
    render();
    save();
    return;
  }

  // Map class prefix to field name (string fields)
  var map = {
    fsd: "send",
    fep: "expect",
    foe: "on_error",
    fmt: "method",
    ful: "url",
    fcm: "command",
    ftg: "target",
    fif: "if",
    fdev: "device",
  };
  for (var k in map) {
    if (cls.includes(k)) {
      steps[idx][map[k]] = el.value;
      save();
      return;
    }
  }

  // Numeric fields
  var nmap = { fto: "timeout", fdr: "duration", fmx: "max_iterations", pto: "timeout" };
  for (var nk in nmap) {
    if (cls.includes(nk)) {
      steps[idx][nmap[nk]] = parseInt(el.value) || 0;
      save();
      return;
    }
  }
});

// ── Input events ──

$("slist").addEventListener("input", function (e) {
  var el = e.target,
    cls = Array.from(el.classList),
    idx = parseInt(el.dataset.idx);
  if (isNaN(idx) || !steps[idx]) return;

  // Capture key/value
  if (cls.includes("capk") || cls.includes("capv")) {
    var old = el.dataset.cap;
    steps[idx].capture = steps[idx].capture || {};
    if (cls.includes("capk")) {
      var val = steps[idx].capture[old];
      delete steps[idx].capture[old];
      steps[idx].capture[el.value || old] = val;
      render();
    } else {
      steps[idx].capture[old] = el.value;
    }
    save();
    return;
  }

  // Branch fields
  if (cls.includes("bif") || cls.includes("bsid") || cls.includes("bval")) {
    var j = parseInt(el.dataset.bidx),
      b = normalizeBranch(steps[idx].branches[j], j),
      inner = b.steps[0];
    if (cls.includes("bif")) {
      if (el.value == "default") {
        delete b.if;
        b.default = true;
      } else {
        delete b.default;
        b.if = el.value;
      }
    } else if (cls.includes("bsid")) {
      inner.id = el.value;
    } else if (cls.includes("bval")) {
      if (inner.type == "serial") inner.send = el.value;
      else if (inner.type == "http") inner.url = el.value;
      else if (inner.type == "script") inner.command = el.value;
      else if (inner.type == "wait") inner.duration = parseInt(el.value) || 0;
      else if (inner.type == "action_batch") {
        try {
          inner.actions = JSON.parse(el.value);
        } catch (e) {}
      }
    }
    steps[idx].branches[j] = b;
    save();
    return;
  }

  // Parallel step fields
  if (cls.includes("psid") || cls.includes("pval")) {
    var pj = parseInt(el.dataset.pidx),
      par = steps[idx].steps || [],
      pinner = par[pj] || {};
    if (cls.includes("psid")) pinner.id = el.value;
    else if (cls.includes("pval")) {
      if (pinner.type == "serial") pinner.send = el.value;
      else if (pinner.type == "http") pinner.url = el.value;
      else if (pinner.type == "script") pinner.command = el.value;
      else if (pinner.type == "wait") pinner.duration = parseInt(el.value) || 0;
      else if (pinner.type == "action_batch") {
        try {
          pinner.actions = JSON.parse(el.value);
        } catch (e) {}
      }
    }
    par[pj] = pinner;
    steps[idx].steps = par;
    save();
    return;
  }

  // Other string fields
  var map = {
    fi: "id",
    fsd: "send",
    fep: "expect",
    ful: "url",
    fcm: "command",
    ftg: "target",
    fif: "if",
  };
  for (var k in map) {
    if (cls.includes(k)) {
      steps[idx][map[k]] = el.value;
      save();
      return;
    }
  }
});