"use strict";
// ── Click events: context menu, add/remove, toggle, drag ──

function showCtx(e, i) {
  e.preventDefault();
  e.stopPropagation();
  ctxIdx = i;
  var m = $("ctxMenu");
  m.style.left = Math.min(e.clientX, window.innerWidth - 160) + "px";
  m.style.top = Math.min(e.clientY, window.innerHeight - 200) + "px";
  m.classList.add("show");
}

function hideCtx() {
  $("ctxMenu").classList.remove("show");
}

function doCtx(a) {
  if (ctxIdx < 0) return;
  if (a == "del") {
    var did = steps[ctxIdx] && steps[ctxIdx].id;
    if (did) {
      delete selected[did];
      if (openId == did) openId = null;
    }
    steps.splice(ctxIdx, 1);
    render();
    save();
    toast("已删除");
  } else if (a == "dup") {
    var s = JSON.parse(JSON.stringify(steps[ctxIdx]));
    s.id = "s" + nid++;
    steps.splice(ctxIdx + 1, 0, s);
    render();
    save();
    toast("复制成功");
  } else if (a == "up") {
    if (ctxIdx > 0) {
      var t = steps[ctxIdx];
      steps[ctxIdx] = steps[ctxIdx - 1];
      steps[ctxIdx - 1] = t;
      render();
      save();
    }
  } else if (a == "dn") {
    if (ctxIdx < steps.length - 1) {
      var t = steps[ctxIdx];
      steps[ctxIdx] = steps[ctxIdx + 1];
      steps[ctxIdx + 1] = t;
      render();
      save();
    }
  }
  hideCtx();
}

// ── Click event delegation ──

$("slist").addEventListener("click", function (e) {
  var t = e.target;

  // Capture add/remove
  if (t.closest(".addcap")) {
    var aci = parseInt(t.closest(".addcap").dataset.idx);
    if (steps[aci]) {
      steps[aci].capture = steps[aci].capture || {};
      var n = "var" + (Object.keys(steps[aci].capture).length + 1);
      steps[aci].capture[n] = "(.+)";
      render();
      save();
    }
    return;
  }
  if (t.closest(".delcap")) {
    var dci = parseInt(t.closest(".delcap").dataset.idx),
      ck = t.closest(".delcap").dataset.cap;
    if (steps[dci] && steps[dci].capture) {
      delete steps[dci].capture[ck];
      render();
      save();
    }
    return;
  }

  // First-iteration checkbox
  if (t.closest(".ffirst")) {
    var fidx = parseInt(t.closest(".ffirst").dataset.idx);
    if (steps[fidx]) {
      if (t.closest(".ffirst").checked) steps[fidx].if = FIRST_EXPR;
      else if (steps[fidx].if == FIRST_EXPR) delete steps[fidx].if;
      render();
      save();
    }
    return;
  }

  // stop_on_failure checkbox
  if (t.closest(".psf")) {
    var sfx = parseInt(t.closest(".psf").dataset.idx);
    if (steps[sfx]) {
      steps[sfx].stop_on_failure = t.closest(".psf").checked;
      save();
    }
    return;
  }

  // Enable/disable toggle
  if (t.closest(".en")) {
    var ei = parseInt(t.closest(".en").dataset.idx);
    if (steps[ei]) {
      if (isOff(steps[ei])) delete steps[ei].enabled;
      else steps[ei].enabled = false;
      render();
      save();
    }
    return;
  }

  // Add/remove branch
  if (t.closest(".addbr")) {
    var ai = parseInt(t.closest(".addbr").dataset.idx);
    if (steps[ai]) {
      steps[ai].branches = steps[ai].branches || [];
      steps[ai].branches.push({
        id: "branch_" + (steps[ai].branches.length + 1),
        steps: [blankStep("serial", "b" + (steps[ai].branches.length + 1))],
      });
      render();
      save();
    }
    return;
  }
  if (t.closest(".bdel")) {
    var bi = parseInt(t.closest(".bdel").dataset.idx),
      bj = parseInt(t.closest(".bdel").dataset.bidx);
    if (steps[bi] && confirm("删除该分支?")) {
      steps[bi].branches.splice(bj, 1);
      render();
      save();
    }
    return;
  }

  // Add/remove parallel step
  if (t.closest(".addps")) {
    var pi = parseInt(t.closest(".addps").dataset.idx);
    if (steps[pi]) {
      steps[pi].steps = steps[pi].steps || [];
      steps[pi].steps.push(blankStep("serial", "p" + (steps[pi].steps.length + 1)));
      render();
      save();
    }
    return;
  }
  if (t.closest(".pdel")) {
    var pii = parseInt(t.closest(".pdel").dataset.idx),
      pj = parseInt(t.closest(".pdel").dataset.pidx);
    if (steps[pii] && steps[pii].steps && confirm("删除该子步骤?")) {
      steps[pii].steps.splice(pj, 1);
      render();
      save();
    }
    return;
  }

  // Selection checkbox
  if (t.closest(".ck")) {
    var ci = parseInt(t.closest(".ck").dataset.idx),
      id = steps[ci] && steps[ci].id;
    if (id) {
      selected[id] = t.closest(".ck").checked;
      if (!selected[id]) delete selected[id];
      render();
    }
    return;
  }

  // Delete button
  if (t.closest(".del")) {
    var i = parseInt(t.closest(".del").dataset.idx);
    if (!isNaN(i) && steps[i] && confirm("删除?")) {
      var id = steps[i].id;
      delete selected[id];
      if (openId == id) openId = null;
      steps.splice(i, 1);
      render();
      save();
      toast("已删除");
    }
    return;
  }

  // Toggle card detail
  var hdr = t.closest(".sc-hdr");
  if (hdr && !t.closest(".del") && !t.closest(".dg") && !t.closest(".ck")) {
    var idx = parseInt(hdr.dataset.idx);
    openId = openId == (steps[idx] && steps[idx].id) ? null : steps[idx] && steps[idx].id;
    render();
  }
});

// Context menu
$("slist").addEventListener("contextmenu", function (e) {
  var hdr = e.target.closest(".sc-hdr");
  if (hdr) {
    showCtx(e, parseInt(hdr.dataset.idx));
    return;
  }
});

document.querySelectorAll(".ci").forEach(function (el) {
  el.addEventListener("click", function () {
    doCtx(this.dataset.idx);
  });
});
document.addEventListener("click", function (e) {
  if (e.button === 0) hideCtx();
});

// ── Palette drag ──

var _dt = null,
  _nativeDrag = false,
  _sx = 0,
  _sy = 0,
  _dg = null,
  _moved = false;

document.addEventListener("dragstart", function (e) {
  var pi = e.target.closest(".pi");
  if (pi) {
    _nativeDrag = true;
    e.dataTransfer.setData("text/ac-step-type", pi.dataset.type);
    pi.classList.add("dragging");
  }
});
document.addEventListener("dragend", function (e) {
  var pi = e.target.closest(".pi");
  if (pi) pi.classList.remove("dragging");
  setDrop(false);
  _nativeDrag = false;
});

function setDrop(on) {
  $("slist").classList.toggle("drop-on", on);
}

function inSlist(x, y) {
  var r = $("slist").getBoundingClientRect();
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
}

function dropIndex(y) {
  var cards = Array.from($("slist").querySelectorAll(".sc"));
  for (var i = 0; i < cards.length; i++) {
    var r = cards[i].getBoundingClientRect();
    if (y < r.top + r.height / 2) return i;
  }
  return cards.length;
}

$("slist").addEventListener("dragover", function (e) {
  if (Array.from(e.dataTransfer.types).indexOf("text/ac-step-type") < 0) return;
  e.preventDefault();
  setDrop(true);
});
$("slist").addEventListener("dragleave", function (e) {
  setDrop(false);
});
$("slist").addEventListener("drop", function (e) {
  e.preventDefault();
  setDrop(false);
  var type = e.dataTransfer.getData("text/ac-step-type");
  if (type) addStep(type, dropIndex(e.clientY));
});

// Mouse drag fallback (for non-native HTML5 drag)
document.addEventListener("mousedown", function (e) {
  var pi = e.target.closest(".pi");
  if (!pi || pi.dataset.dragDisabled) return;
  _dt = pi.dataset.type;
  _nativeDrag = false;
  _sx = e.clientX;
  _sy = e.clientY;
  _moved = false;
  _dg = null;
});
document.addEventListener("mousemove", function (e) {
  if (!_dt || _nativeDrag) return;
  if (!_moved && Math.abs(e.clientX - _sx) + Math.abs(e.clientY - _sy) > 6) {
    _moved = true;
    _dg = document.createElement("div");
    _dg.textContent = "+ " + _dt;
    _dg.style.cssText = "position:fixed;pointer-events:none;z-index:999;background:#3b82f6;color:#fff;padding:3px 10px;border-radius:5px;font-size:12px;opacity:.8;";
    document.body.appendChild(_dg);
  }
  if (_dg) {
    _dg.style.left = e.clientX + 10 + "px";
    _dg.style.top = e.clientY - 6 + "px";
    setDrop(inSlist(e.clientX, e.clientY));
  }
});
document.addEventListener("mouseup", function (e) {
  if (!_dt || _nativeDrag) return;
  if (_dg) {
    document.body.removeChild(_dg);
    _dg = null;
  }
  setDrop(false);
  if (_moved && inSlist(e.clientX, e.clientY)) addStep(_dt, dropIndex(e.clientY));
  _dt = null;
});