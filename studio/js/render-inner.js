"use strict";
// ── Inner step rendering: capture, branch, parallel ──

function captureHTML(i, k, v) {
  return (
    '<div class="cap-row" data-idx="' +
    i +
    '" data-cap="' +
    esc(k) +
    '"><div class="fr"><div class="fg fs" style="min-width:120px"><label>变量名</label><input class="capk" data-idx="' +
    i +
    '" data-cap="' +
    esc(k) +
    '" value="' +
    esc(k) +
    '"></div><div class="fg"><label>正则表达式</label><input class="capv" data-idx="' +
    i +
    '" data-cap="' +
    esc(k) +
    '" value="' +
    esc(v) +
    '" placeholder="FW:([0-9.]+)"></div><button type="button" class="mini-del delcap" data-idx="' +
    i +
    '" data-cap="' +
    esc(k) +
    '"><i class="fa-regular fa-trash-can"></i></button></div></div>'
  );
}

function branchHTML(b, i, j) {
  b = b || {};
  var def = !!b.default,
    inner = (b.steps && b.steps[0]) || {};
  var h =
    '<div class="branch" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '"><div class="branch-head"><span><i class="fa-solid fa-diagram-project"></i> 分支 ' +
    (j + 1) +
    '</span><button type="button" class="bdel" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '"><i class="fa-regular fa-trash-can"></i></button></div>';
  h +=
    '<div class="fr"><div class="fg fs" style="min-width:110px"><label>条件类型</label><select class="bdf" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '"><option value="0">if</option><option value="1"' +
    (def ? " selected" : "") +
    ">default</option></select></div>";
  h +=
    '<div class="fg"><label>条件</label><input class="bif" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '" value="' +
    esc(def ? "default" : b.if || "") +
    '" placeholder="例如 {{ last.status }} == passed"></div></div>';
  h +=
    '<div class="fr"><div class="fg fs" style="min-width:110px"><label>执行类型</label><select class="bst" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '">' +
    TPL.filter(function (t) {
      return TI[t].k != "logic";
    })
      .map(function (t) {
        return "<option" + (inner.type == t ? " selected" : "") + ">" + t + "</option>";
      })
      .join("") +
    "</select></div>";
  h +=
    '<div class="fg"><label>分支步骤 ID</label><input class="bsid" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '" value="' +
    esc(inner.id || "b" + (j + 1)) +
    '"></div>';
  h +=
    '<div class="fg"><label>主要内容</label><input class="bval" data-idx="' +
    i +
    '" data-bidx="' +
    j +
    '" value="' +
    esc(inner.send || inner.url || inner.command || inner.duration || "") +
    '" placeholder="serial send / http url / script command / wait ms"></div></div></div>';
  return h;
}

function normalizeBranch(b, j) {
  b = b || {};
  if (!b.steps) b.steps = [];
  if (!b.steps[0])
    b.steps[0] = {
      id: "b" + (j + 1),
      type: "serial",
      send: "AT+",
      expect: "OK",
      timeout: 3000,
    };
  return b;
}

function setBranchStep(i, j, t) {
  var b = normalizeBranch(steps[i].branches[j], j),
    old = b.steps[0] || {},
    n = blankStep(t, old.id || "b" + (j + 1));
  if (t == "serial" && old.send) n.send = old.send;
  if (t == "http" && old.url) n.url = old.url;
  if (t == "script" && old.command) n.command = old.command;
  if (t == "wait" && old.duration) n.duration = old.duration;
  b.steps[0] = n;
  steps[i].branches[j] = b;
}

function parallelStepHTML(p, i, j) {
  p = p || {};
  var h =
    '<div class="branch" data-idx="' +
    i +
    '" data-pidx="' +
    j +
    '"><div class="branch-head"><span><i class="fa-solid fa-arrow-right-arrow-left"></i> 子步骤 ' +
    (j + 1) +
    '</span><button type="button" class="pdel" data-idx="' +
    i +
    '" data-pidx="' +
    j +
    '"><i class="fa-regular fa-trash-can"></i></button></div>';
  h +=
    '<div class="fr"><div class="fg fs" style="min-width:110px"><label>执行类型</label><select class="pst" data-idx="' +
    i +
    '" data-pidx="' +
    j +
    '">' +
    TPL.filter(function (t) {
      return TI[t].k != "logic";
    })
      .map(function (t) {
        return "<option" + (p.type == t ? " selected" : "") + ">" + t + "</option>";
      })
      .join("") +
    "</select></div>";
  h +=
    '<div class="fg"><label>子步骤 ID</label><input class="psid" data-idx="' +
    i +
    '" data-pidx="' +
    j +
    '" value="' +
    esc(p.id || "p" + (j + 1)) +
    '"></div>';
  h +=
    '<div class="fg"><label>主要内容</label><input class="pval" data-idx="' +
    i +
    '" data-pidx="' +
    j +
    '" value="' +
    esc(p.send || p.url || p.command || p.duration || "") +
    '" placeholder="serial send / http url / script command / wait ms"></div></div></div>';
  return h;
}

function setParallelStep(i, j, t) {
  var stepsArr = steps[i].steps || [],
    old = stepsArr[j] || {},
    n = blankStep(t, old.id || "p" + (j + 1));
  if (t == "serial" && old.send) n.send = old.send;
  if (t == "http" && old.url) n.url = old.url;
  if (t == "script" && old.command) n.command = old.command;
  if (t == "wait" && old.duration) n.duration = old.duration;
  stepsArr[j] = n;
  steps[i].steps = stepsArr;
}