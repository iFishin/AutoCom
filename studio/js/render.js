"use strict";
// ── Rendering: step cards, config panels, modals ──

function blankStep(t, id) {
  var s = { id: id, type: t };
  if (t == "serial") {
    s.device = devs()[0].name;
    s.send = "AT+";
    s.expect = "OK";
    s.timeout = 3000;
    s.capture = {};
  } else if (t == "serial_wait") {
    s.device = devs()[0].name;
    s.expect = "RDY";
    s.timeout = 60000;
    s.capture = {};
  } else if (t == "http") {
    s.url = "";
    s.method = "GET";
  } else if (t == "wait") {
    s.duration = 1000;
  } else if (t == "action_batch") {
    s.actions = [{ print: "" }];
  } else if (t == "goto") {
    s.target = "";
    s.max_iterations = 3;
  } else if (t == "choose") {
    s.branches = [];
  } else if (t == "parallel") {
    s.steps = [];
  }
  return s;
}

function mkStep(t) {
  return blankStep(t, "s" + nid++);
}

function addStep(t, idx) {
  var s = mkStep(t);
  if (typeof idx == "number" && idx >= 0 && idx <= steps.length) steps.splice(idx, 0, s);
  else steps.push(s);
  render();
  save();
  toast("+ " + t);
}

function changeType(i, t) {
  var o = steps[i],
    n = mkStep(t);
  n.id = o.id;
  openId = o.id;
  steps[i] = n;
  render();
  save();
  toast("-> " + t);
}

function renderVars() {
  var g = $("varGrid"),
    cur = "";
  g.innerHTML = VARS.map(function (v) {
    var h = "";
    if (v[0] != cur) {
      cur = v[0];
      h = '<div class="vsec">' + cur + "</div>";
    }
    return h + '<div class="vcard" data-v="' + esc(v[1]) + '"><div class="vcode">' + esc(v[1]) + '</div><div class="vdesc">' + esc(v[2]) + "</div></div>";
  }).join("");
}

function renderDevices() {
  $("devList").innerHTML = devices
    .map(function (d, i) {
      return '<div class="dev-row"><div class="fr"><div class="fg fs" style="min-width:100px"><label>名称</label><input class="dnm" data-didx="' + i + '" value="' + esc(d.name) + '"></div><div class="fg fs" style="min-width:100px"><label>串口</label><input class="dpt" data-didx="' + i + '" value="' + esc(d.port) + '" placeholder="COM16"></div><div class="fg fs" style="min-width:90px"><label>波特率</label><input class="dbd" data-didx="' + i + '" type="number" value="' + (d.baud_rate || 115200) + '"></div>' +
        (devices.length > 1 ? '<button type="button" class="mini-del deldev" data-didx="' + i + '"><i class="fa-regular fa-trash-can"></i></button>' : "") +
        "</div></div>";
    })
    .join("");
}

function bodyHTML(s, i) {
  var h =
    '<div class="fr"><div class="fg fs" style="min-width:90px"><label>类型</label><select class="ft" data-idx="' +
    i +
    '">' +
    TPL.map(function (t) {
      return "<option" + sel(s.type, t) + ">" + t + "</option>";
    }).join("") +
    "</select></div>";
  h +=
    '<div class="fg fs"><label>ID</label><input class="fi" value="' +
    esc(s.id) +
    '" data-idx="' +
    i +
    '"></div></div>';

  if (s.type == "serial") {
    if (!s.device) s.device = devs()[0].name;
    if (!s.capture) s.capture = {};
    h +=
      '<div class="fr"><div class="fg fs" style="min-width:120px"><label>设备</label><select class="fdev" data-idx="' +
      i +
      '">' +
      deviceOptions(s.device) +
      "</select></div>";
    h +=
      '<div class="fg"><label>Send</label><input class="fsd" value="' +
      esc(opt(s.send, "")) +
      '" data-idx="' +
      i +
      '"></div><div class="fg fs"><label>Expect</label><input class="fep" value="' +
      esc(opt(s.expect, "")) +
      '" data-idx="' +
      i +
      '"></div></div>';
    h +=
      '<div class="fr"><div class="fg fs"><label>Timeout</label><input class="fto" type="number" value="' +
      (s.timeout || 3000) +
      '" data-idx="' +
      i +
      '"></div></div>';
    h +=
      '<div class="fr"><label style="display:flex;align-items:center;gap:5px;color:#94a3b8;font-size:11px"><input class="ffirst" type="checkbox" data-idx="' +
      i +
      '" ' +
      (s.if == FIRST_EXPR ? "checked" : "") +
      '> 仅首次迭代执行</label><div class="fg"><label>If 条件</label><input class="fif" value="' +
      esc(opt(s.if, "")) +
      '" data-idx="' +
      i +
      '" placeholder="例如 {{ session.iteration }} == 1"></div></div>';
    h +=
      '<div class="logic-panel"><div class="logic-title"><i class="fa-solid fa-filter"></i> Capture 提取变量</div>';
    var keys = Object.keys(s.capture || {});
    if (!keys.length)
      h +=
        '<div class="ht" style="margin-bottom:7px">可从响应中用正则提取变量，例如 version = FW:([0-9.]+)</div>';
    keys.forEach(function (k) {
      h += captureHTML(i, k, s.capture[k]);
    });
    h +=
      '<button type="button" class="btn btn-o addcap" data-idx="' +
      i +
      '"><i class="fa-solid fa-plus"></i> 添加捕获变量</button></div>';
  } else if (s.type == "serial_wait") {
    if (!s.device) s.device = devs()[0].name;
    if (!s.capture) s.capture = {};
    h +=
      '<div class="fr"><div class="fg fs" style="min-width:120px"><label>设备</label><select class="fdev" data-idx="' +
      i +
      '">' +
      deviceOptions(s.device) +
      '</select></div><div class="fg"><label>Expect</label><input class="fep" value="' +
      esc(opt(s.expect, "")) +
      '" data-idx="' +
      i +
      '" placeholder="等待的串口响应"></div><div class="fg fs"><label>Timeout</label><input class="fto" type="number" value="' +
      (s.timeout || 60000) +
      '" data-idx="' +
      i +
      '"></div></div>';
    h +=
      '<div class="fr"><label style="display:flex;align-items:center;gap:5px;color:#94a3b8;font-size:11px"><input class="ffirst" type="checkbox" data-idx="' +
      i +
      '" ' +
      (s.if == FIRST_EXPR ? "checked" : "") +
      '> 仅首次迭代执行</label><div class="fg"><label>If 条件</label><input class="fif" value="' +
      esc(opt(s.if, "")) +
      '" data-idx="' +
      i +
      '" placeholder="例如 {{ session.iteration }} == 1"></div></div>';
    h +=
      '<div class="logic-panel"><div class="logic-title"><i class="fa-solid fa-filter"></i> Capture 提取变量</div>';
    var wkeys = Object.keys(s.capture || {});
    if (!wkeys.length)
      h +=
        '<div class="ht" style="margin-bottom:7px">可从等待到的串口输出中提取变量。</div>';
    wkeys.forEach(function (k) {
      h += captureHTML(i, k, s.capture[k]);
    });
    h +=
      '<button type="button" class="btn btn-o addcap" data-idx="' +
      i +
      '"><i class="fa-solid fa-plus"></i> 添加捕获变量</button></div>';
  } else if (s.type == "http") {
    h +=
      '<div class="fr"><div class="fg fs"><label>Method</label><select class="fmt" data-idx="' +
      i +
      '">' +
      ["GET", "POST", "PUT", "DELETE"]
        .map(function (m) {
          return "<option" + sel(s.method, m) + ">" + m + "</option>";
        })
        .join("") +
      "</select></div>";
    h +=
      '<div class="fg"><label>URL</label><input class="ful" value="' +
      esc(opt(s.url, "")) +
      '" data-idx="' +
      i +
      '"></div></div>';
  } else if (s.type == "script") {
    h +=
      '<div class="fr"><div class="fg"><label>Command</label><input class="fcm" value="' +
      esc(opt(s.command, "")) +
      '" data-idx="' +
      i +
      '"></div></div>';
  } else if (s.type == "wait") {
    h +=
      '<div class="fr"><div class="fg fs"><label>Duration (ms)</label><input class="fdr" type="number" value="' +
      (s.duration || 1000) +
      '" data-idx="' +
      i +
      '"></div></div>';
  } else if (s.type == "action_batch") {
    h +=
      '<div class="fr"><div class="fg"><label>Actions</label><textarea class="fac" data-idx="' +
      i +
      '" rows="2">' +
      esc(JSON.stringify(s.actions || [])) +
      "</textarea></div></div>";
  } else if (s.type == "goto") {
    h +=
      '<div class="logic-panel"><div class="logic-title"><i class="fa-solid fa-route"></i> 跳转规则</div>';
    h +=
      '<div class="jump-line"><span class="node-pill">当前 ' +
      esc(s.id) +
      '</span><span class="arrow"><i class="fa-solid fa-arrow-right-long"></i></span><span class="node-pill">' +
      esc(s.target || "未选择目标") +
      "</span></div>";
    h +=
      '<div class="fr"><div class="fg"><label>跳转目标</label><select class="ftg" data-idx="' +
      i +
      '">' +
      targetOptions(s.target) +
      '</select></div><div class="fg fs"><label>最大次数</label><input class="fmx" type="number" min="0" value="' +
      (s.max_iterations || 3) +
      '" data-idx="' +
      i +
      '"></div></div>';
    h +=
      '<div class="fr"><div class="fg"><label>跳转条件</label><input class="fif" value="' +
      esc(opt(s.if, "")) +
      '" data-idx="' +
      i +
      '" placeholder="留空表示无条件跳转"></div></div></div>';
  } else if (s.type == "choose") {
    var bs = s.branches || [];
    h +=
      '<div class="logic-panel"><div class="logic-title"><i class="fa-solid fa-code-branch"></i> 分支规则</div>';
    if (!bs.length) h += '<div class="ht" style="margin-bottom:7px">还没有分支，点击下方按钮添加。</div>';
    bs.forEach(function (b, j) {
      h += branchHTML(normalizeBranch(b, j), i, j);
    });
    h +=
      '<button type="button" class="btn btn-o addbr" data-idx="' +
      i +
      '"><i class="fa-solid fa-plus"></i> 添加分支</button></div>';
  } else if (s.type == "parallel") {
    var ps = s.steps || [];
    h +=
      '<div class="logic-panel"><div class="logic-title"><i class="fa-solid fa-layer-group"></i> 并行子步骤</div>';
    if (!ps.length) h += '<div class="ht" style="margin-bottom:7px">还没有子步骤，点击下方按钮添加。</div>';
    ps.forEach(function (p, j) {
      h += parallelStepHTML(p, i, j);
    });
    h +=
      '<button type="button" class="btn btn-o addps" data-idx="' +
      i +
      '"><i class="fa-solid fa-plus"></i> 添加子步骤</button></div>';
    h +=
      '<div class="fr" style="margin-top:7px"><div class="fg fs"><label>超时 (秒)</label><input class="pto" type="number" min="0" value="' +
      (s.timeout || 0) +
      '" data-idx="' +
      i +
      '"></div>';
    h +=
      '<div class="fg fs"><label style="display:flex;align-items:center;gap:5px;color:#94a3b8;font-size:12px"><input class="psf" type="checkbox" data-idx="' +
      i +
      '" ' +
      (s.stop_on_failure ? "checked" : "") +
      '> stop_on_failure</label></div></div>';
  }
  return h;
}

function render() {
  var listEl = $("sortableList"),
    emptyEl = $("empty"),
    endEl = $("connEnd");
  if (steps.length == 0) {
    if (sortable) {
      sortable.destroy();
      sortable = null;
    }
    listEl.innerHTML = "";
    emptyEl.style.display = "";
    endEl.style.display = "none";
    setBulkUI();
    return;
  }
  emptyEl.style.display = "none";
  endEl.style.display = "";
  var alive = {};
  steps.forEach(function (s) {
    alive[s.id] = 1;
  });
  for (var id in selected) {
    if (!alive[id]) delete selected[id];
  }
  listEl.innerHTML = steps
    .map(function (s, i) {
      var off = isOff(s);
      var t = TI[s.type] || { c: "#64748b", i: "circle", l: s.type };
      var tip = "类型: " + t.l + (t.k == "logic" ? " (流程控制)" : " (执行步骤)");
      var h =
        '<div class="sc' +
        (t.k == "logic" ? " logic" : "") +
        (selected[s.id] ? " sel" : "") +
        (off ? " off" : "") +
        '" data-idx="' +
        i +
        '"><div class="sc-hdr" data-idx="' +
        i +
        '">';
      h += '<span class="dg" title="拖拽排序"><i class="fa-solid fa-grip-vertical"></i></span>';
      h += '<input class="ck" type="checkbox" data-idx="' + i + '" ' + (selected[s.id] ? "checked" : "") + ' title="选择/取消">';
      h += '<button type="button" class="en" data-idx="' + i + '" title="' + (off ? "点击启用此步骤" : "点击禁用此步骤") + '"><i class="fa-solid ' + (off ? "fa-toggle-off" : "fa-toggle-on") + '"></i></button>';
      h += '<span class="badge" style="background:' + t.c + "22;color:" + t.c + '" title="' + tip + '"><i class="type-ico fa-solid fa-' + t.i + '"></i> ' + t.l + "</span>";
      h += '<span class="sid" title="步骤标识符: ' + esc(s.id) + '">' + s.id + '</span><span class="ssum" title="步骤摘要">' + (off ? "已禁用 · " : "") + esc(summary(s)) + '</span><span class="snum" title="执行顺序 #' + (i + 1) + '">#' + (i + 1) + "</span>";
      h += '<button type="button" class="del" data-idx="' + i + '" title="删除此步骤"><i class="fa-regular fa-trash-can"></i></button>';
      h += '<span class="chev' + (openId == s.id ? " open" : "") + '" data-idx="' + i + '" title="' + (openId == s.id ? "折叠" : "展开") + '详情"><i class="fa-solid fa-chevron-down"></i></span></div>';
      h += '<div class="sc-bd' + (openId == s.id ? " open" : "") + '" data-idx="' + i + '">' + bodyHTML(s, i) + "</div></div>";
      return h;
    })
    .join("");
  setBulkUI();
  if (sortable) sortable.destroy();
  sortable = new Sortable(listEl, {
    draggable: ".sc",
    handle: ".sc-hdr",
    filter: ".ck,.en,.del,.chev,input,select,textarea,button",
    preventOnFilter: false,
    forceFallback: true,
    fallbackTolerance: 5,
    animation: 150,
    ghostClass: "sortable-ghost",
    onEnd: function (evt) {
      var from = evt.oldIndex,
        to = evt.newIndex;
      if (typeof from !== "number" || typeof to !== "number" || from === to) return;
      if (from < 0 || from >= steps.length || to < 0 || to >= steps.length) return;
      var m = steps.splice(from, 1);
      steps.splice(to, 0, m[0]);
      save();
      render();
    },
  });
}