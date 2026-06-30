"use strict";
// ── Utilities: type info, constants, helpers ──

var FIRST_EXPR = "{{ session.iteration }} == 1";

var TI = {
  serial: { c: "#60a5fa", i: "microchip", l: "serial", k: "step" },
  serial_wait: { c: "#38bdf8", i: "satellite-dish", l: "wait serial", k: "step" },
  http: { c: "#4ade80", i: "globe", l: "http", k: "step" },
  script: { c: "#fbbf24", i: "terminal", l: "script", k: "step" },
  wait: { c: "#c084fc", i: "hourglass-half", l: "wait", k: "step" },
  action_batch: { c: "#f472b6", i: "list-check", l: "action", k: "step" },
  choose: { c: "#22d3ee", i: "code-branch", l: "choose", k: "logic" },
  goto: { c: "#fb923c", i: "arrow-turn-up", l: "goto", k: "logic" },
  parallel: { c: "#a78bfa", i: "layer-group", l: "parallel", k: "logic" },
};
var TPL = Object.keys(TI);

var VARS = [
  ["步骤", "{{ steps.s1.status }}", "passed / failed / skipped / error"],
  ["步骤", "{{ steps.s1.response }}", "原始响应文本"],
  ["步骤", "{{ steps.s1.capture.xxx }}", "某步骤 capture 提取的变量"],
  ["旧语法", "{version}", "模糊搜索 capture/constants/devices/session"],
  ["设备", "{{ devices.DeviceA.port }}", "设备串口号"],
  ["设备", "{{ devices.DeviceA.baud_rate }}", "设备波特率"],
  ["会话", "{{ session.iteration }}", "当前迭代序号"],
  ["会话", "{{ session.total }}", "总迭代次数"],
  ["过滤器", '{{ steps.s1.capture.rssi | int }}', "转为整数"],
  ["过滤器", '{{ steps.s1.response | lower }}', "转为小写"],
];

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/'/g, "&#39;");
}

function deviceOptions(v) {
  return devs()
    .map(function (d) {
      return '<option value="' + esc(d.name) + '"' + (d.name == v ? " selected" : "") + ">" + esc(d.name + " · " + d.port) + "</option>";
    })
    .join("");
}

function targetOptions(v) {
  return (
    '<option value="">后续执行</option>' +
    steps
      .map(function (s) {
        return '<option value="' + esc(s.id) + '"' + (s.id == v ? " selected" : "") + ">" + esc(s.id + " · " + s.type) + "</option>";
      })
      .join("")
  );
}

function isOff(s) {
  return s.enabled === false || String(s.status || "").toLowerCase() == "disabled";
}

function summary(s) {
  if (s.type == "serial")
    return (s.device ? "[" + s.device + "] " : "") + (s.send ? "Send: " + s.send : "");
  if (s.type == "serial_wait")
    return (s.device ? "[" + s.device + "] " : "") + "等待 " + (s.expect || "串口响应");
  if (s.type == "http") return (s.method || "GET") + " " + (s.url || "");
  if (s.type == "script") return s.command || "";
  if (s.type == "wait") return (s.duration || 0) + "ms";
  if (s.type == "action_batch") return (s.actions || []).length + " actions";
  if (s.type == "goto")
    return s.target ? "跳转到 " + s.target + (s.if ? " · 条件跳转" : "") : "未选择目标";
  if (s.type == "choose")
    return (s.branches || [])
      .map(function (b) {
        return (b.default ? "default" : b.if || "always") + " → " + (b.steps && b.steps.length ? b.steps.length + " steps" : "空分支");
      })
      .join(" / ") || "未配置分支";
  if (s.type == "parallel")
    return (s.steps || []).length + " steps 并行" + (s.timeout ? " · " + s.timeout + "s 超时" : "");
  return "";
}

function opt(v, d) {
  return v !== undefined ? v : d;
}
function sel(o, v) {
  return o == v ? " selected" : "";
}