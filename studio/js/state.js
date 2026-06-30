"use strict";
// ── State: steps, devices, save/restore, localStorage ──

var steps = [],
  devices = [],
  nid = 1,
  ctxIdx = -1,
  sortable = null,
  selected = {},
  openId = null,
  lastEdit = null;

function $(id) {
  return document.getElementById(id);
}

function devs() {
  if (!devices.length)
    devices = [{ name: "DeviceA", port: "COM16", baud_rate: 115200 }];
  return devices;
}

function save() {
  try {
    localStorage.setItem(
      "ac_studio",
      JSON.stringify({
        md: $("inpMode").value,
        it: $("inpIter").value,
        iv: $("inpInterval").value,
        dc: $("inpDesc").value,
        st: steps,
        ds: devices,
        ni: nid,
      }),
    );
  } catch (e) {}
}

function restore() {
  try {
    var s = JSON.parse(localStorage.getItem("ac_studio"));
    if (!s) return false;
    if (s.md) $("inpMode").value = s.md;
    if (s.it) $("inpIter").value = s.it;
    if (s.iv) $("inpInterval").value = s.iv;
    if (s.dc !== undefined) $("inpDesc").value = s.dc;
    if (s.ds) devices = s.ds;
    if (!devices.length) devs();
    if (s.st) steps = s.st;
    if (s.ni) nid = s.ni;
    return true;
  } catch (e) {
    return false;
  }
}

function setBulkUI() {
  var ids = steps.map(function (s) { return s.id; });
  var cnt = ids.filter(function (id) { return selected[id]; }).length;
  $("btnDelSel").disabled = cnt == 0;
}

function syncModeUI() {
  var m = $("inpMode").value;
  $("topBar").className = "db mode-" + m;
}