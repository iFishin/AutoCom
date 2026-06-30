"use strict";
// ── Initialization: import/export, modals, keyboard, auto-save ──

function toast(msg) {
  var el = $("toast");
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(function () {
    el.style.display = "none";
  }, 2000);
}

function closeModal() {
  $("mo").classList.remove("active");
}
function closeVars() {
  $("varMo").classList.remove("active");
}
function closeDevices() {
  $("devMo").classList.remove("active");
}

function genYAML() {
  var mode = $("inpMode").value,
    iter = $("inpIter").value,
    interv = $("inpInterval").value,
    desc = $("inpDesc").value;
  var cfg = { mode: mode };
  if (desc) cfg.description = desc;
  if (mode != "single")
    cfg.loop = {
      iterations: parseInt(iter) || 1,
      interval_ms: parseInt(interv) || 0,
    };
  var out = {
    Devices: devices.map(function (d) {
      return { name: d.name || "DeviceA", port: d.port || "COM16", baud_rate: parseInt(d.baud_rate) || 115200 };
    }),
    Config: cfg,
    Steps: steps.map(function (s) {
      var o = {};
      for (var k in s) {
        if (s[k] !== undefined && s[k] !== null && s[k] !== "" && !(k == "capture" && Object.keys(s[k] || {}).length == 0)) o[k] = s[k];
      }
      return o;
    }),
  };
  return jsyaml.dump(out, { indent: 2, lineWidth: -1, noRefs: true, sortKeys: false });
}

function downloadYAML() {
  var yaml = genYAML();
  var blob = new Blob([yaml], { type: "text/yaml;charset=utf-8" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "pipeline.yaml";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  toast("已下载");
}

function copyYAML() {
  var yaml = genYAML();
  navigator.clipboard.writeText(yaml).then(function () {
    toast("已复制");
  });
}

function useVar(v) {
  closeVars();
  var el = lastEdit;
  if (el && document.contains(el) && (el.tagName == "INPUT" || el.tagName == "TEXTAREA")) {
    var s = el.selectionStart,
      e = el.selectionEnd;
    el.value = el.value.substring(0, s) + v + el.value.substring(e);
    el.selectionStart = el.selectionEnd = s + v.length;
    el.focus();
    el.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    navigator.clipboard.writeText(v).then(function () {
      toast("已复制到剪贴板");
    });
  }
}

function trackEdit(e) {
  lastEdit = e.target;
}

// ── Button bindings ──

$("btnImport").addEventListener("click", function () {
  var inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".yaml,.yml,.json";
  inp.onchange = function (e) {
    var r = new FileReader();
    r.onload = function (ev) {
      try {
        var doc = jsyaml.load(ev.target.result);
        if (doc.Devices && doc.Devices[0]) {
          devices = doc.Devices.map(function (d) {
            return { name: d.name || "", port: d.port || "", baud_rate: d.baud_rate || 115200 };
          });
        }
        if (doc.Config) {
          var dc = doc.Config;
          $("inpMode").value = dc.mode || "single";
          if (dc.description) $("inpDesc").value = dc.description;
          if (dc.loop) {
            $("inpIter").value = dc.loop.iterations || 3;
            $("inpInterval").value = dc.loop.interval_ms || 0;
          }
        } else if (doc.loop) {
          $("inpMode").value = "loop";
          $("inpIter").value = doc.loop || 3;
        }
        syncModeUI();
        if (doc.Steps) {
          steps = doc.Steps.map(function (s) {
            return JSON.parse(JSON.stringify(s));
          });
          selected = {};
          openId = null;
          nid = 1;
          steps.forEach(function (s) {
            var m = parseInt((s.id || "").replace(/[^0-9]/g, "") || 0);
            if (m >= nid) nid = m + 1;
          });
        } else if (doc.Commands) {
          selected = {};
          openId = null;
          steps = doc.Commands.map(function (c, i) {
            return { id: "s" + i, type: "serial", send: c.command || c.send || "", expect: c.expected_responses || c.expect || "OK", timeout: c.timeout || 3000 };
          });
          nid = steps.length + 1;
        }
        render();
        save();
        toast("导入成功");
      } catch (e) {
        toast("导入失败");
      }
    };
    r.readAsText(inp.files[0]);
  };
  inp.click();
});

$("btnPreview").addEventListener("click", function () {
  $("yamlPre").textContent = genYAML();
  $("mo").classList.add("active");
});

$("btnDevices").addEventListener("click", function () {
  renderDevices();
  $("devMo").classList.add("active");
});

$("btnVars").addEventListener("click", function () {
  renderVars();
  $("varMo").classList.add("active");
});

$("btnSave").addEventListener("click", downloadYAML);
$("btnCloseModal").addEventListener("click", closeModal);
$("btnCloseModal2").addEventListener("click", closeModal);
$("btnCloseVars").addEventListener("click", closeVars);
$("btnCloseVars2").addEventListener("click", closeVars);
$("btnCloseDevices").addEventListener("click", closeDevices);
$("btnCloseDevices2").addEventListener("click", closeDevices);
$("btnCopyYAML").addEventListener("click", copyYAML);
$("btnDownloadYAML").addEventListener("click", downloadYAML);
$("btnSelAll").addEventListener("click", function () {
  var ids = steps.map(function (s) { return s.id; });
  var all = ids.length && ids.every(function (id) { return selected[id]; });
  selected = {};
  if (!all) ids.forEach(function (id) { selected[id] = true; });
  render();
});
$("btnDelSel").addEventListener("click", function () {
  var cnt = steps.filter(function (s) { return selected[s.id]; }).length;
  if (!cnt) return;
  if (confirm("删除选中的 " + cnt + " 个步骤?")) {
    steps = steps.filter(function (s) { return !selected[s.id]; });
    selected = {};
    render();
    save();
    toast("已删除 " + cnt + " 个步骤");
  }
});

// Modal overlay clicks
$("mo").addEventListener("click", function (e) {
  if (e.target == this) closeModal();
});
$("varMo").addEventListener("click", function (e) {
  if (e.target == this) closeVars();
  var c = e.target.closest(".vcard");
  if (c) {
    useVar(c.dataset.v);
    closeVars();
  }
});
$("devMo").addEventListener("click", function (e) {
  if (e.target == this) closeDevices();
  var b = e.target.closest(".deldev");
  if (b && devices.length > 1) {
    devices.splice(parseInt(b.dataset.didx), 1);
    renderDevices();
    render();
    save();
  }
});

// Device modal input editing
$("devMo").addEventListener("input", function (e) {
  var el = e.target,
    i = parseInt(el.dataset.didx);
  if (isNaN(i) || !devices[i]) return;
  if (el.classList.contains("dnm")) devices[i].name = el.value;
  else if (el.classList.contains("dpt")) devices[i].port = el.value;
  else if (el.classList.contains("dbd")) devices[i].baud_rate = parseInt(el.value) || 115200;
  render();
  save();
});

$("btnAddDevice").addEventListener("click", function () {
  devices.push({ name: "Device" + (devices.length + 1), port: "COM" + (16 + devices.length), baud_rate: 115200 });
  renderDevices();
  render();
  save();
});

// Auto-save for top bar inputs
["inpMode", "inpIter", "inpInterval", "inpDesc"].forEach(function (id) {
  $(id).addEventListener("input", save);
});
$("inpMode").addEventListener("change", syncModeUI);

// Track last edited input for var insertion
document.addEventListener("focusin", trackEdit);

// ── Keyboard shortcuts ──
document.addEventListener("keydown", function (e) {
  if (e.ctrlKey && e.key == "s") {
    e.preventDefault();
    downloadYAML();
  }
});

// ── Initialization ──
restore();
syncModeUI();
if (steps.length) render();