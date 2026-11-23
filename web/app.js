/* ATOM v13 screen logic.
   Python -> page: ui_web.py calls ATOM.recv([{t: "status"|"level"|"line"|"panels"|"data", ...}]).
   Page -> Python: window.pywebview.api.<name>() (see ui_web.Api). Without pywebview (a plain
   browser or the tests) the page still works on its own with local toggles. */
(function () {
  "use strict";

  var ORDER = ["news", "markets", "chat", "music", "inbox", "reminders"];
  var BRIEFING = ["news", "markets", "chat", "reminders"];
  // Panel rectangles in % of the stage: [left, top, width, height]. The bottom-right corner
  // (x > 84%, y > 71%) stays free for the docked atom. Slots are filled in ORDER priority.
  var LAYOUTS = {
    1: [[13, 2, 64, 96]],
    2: [[0, 0, 49, 100], [51, 0, 49, 69]],
    3: [[0, 0, 56, 100], [58, 0, 42, 48], [58, 51, 25, 49]],
    4: [[0, 0, 56, 100], [58, 0, 42, 30], [58, 32.5, 42, 37], [58, 72, 25, 28]],
    5: [[0, 0, 56, 63], [58, 0, 42, 30], [58, 32.5, 42, 37], [0, 65.5, 56, 34.5], [58, 72, 25, 28]],
    6: [[0, 0, 56, 63], [58, 0, 42, 30], [58, 32.5, 42, 37], [0, 65.5, 27, 34.5], [29, 65.5, 27, 34.5], [58, 72, 25, 28]]
  };
  var MAX_HEIGHT = { music: 50 };   // % of the stage; a tall slot is trimmed for these
  var SMALL_ALONE = { music: [30, 16, 40, 56], reminders: [24, 6, 48, 84], inbox: [20, 4, 56, 92] };
  var DEFAULT_CHANNEL = { name: "CHANNELS TV", id: "UCEXGDNclvmg6RW0vipJYsTQ" };
  var CHANNELS = [DEFAULT_CHANNEL, { name: "ARISE NEWS", id: "UCyEJX-kSj0kOOCS7Qlq2G7g" }];

  var S = {
    state: "idle", status: "Standing by", open: [], briefing: false, live: false, playing: false,
    channel: DEFAULT_CHANNEL, lines: [], data: {}, level: 0, online: true
  };

  function $(id) { return document.getElementById(id); }
  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(n, digits) {
    if (n == null || isNaN(n)) return "—";
    return Number(n).toLocaleString("en-US", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 });
  }
  function pct(n, invert) {
    if (n == null || isNaN(n)) return "";
    var good = invert ? n <= 0 : n >= 0;
    return ' <span class="' + (good ? "up" : "dn") + '">' + (n >= 0 ? "▲" : "▼") + Math.abs(n).toFixed(1) + "%</span>";
  }

  // ---- Bridge to Python ----------------------------------------------------------------
  function api() { return window.pywebview && window.pywebview.api ? window.pywebview.api : null; }
  function call(name) {
    var args = Array.prototype.slice.call(arguments, 1);
    var a = api();
    if (a && typeof a[name] === "function") {
      try { return a[name].apply(a, args); } catch (e) { /* fall through to local */ }
    }
    local(name, args);
    return null;
  }
  function local(name, args) {      // no Python: behave sensibly on our own
    if (name === "toggle") {
      var p = args[0];
      if (p === "core") setPanels([], false, false);
      else if (S.open.indexOf(p) >= 0) setPanels(S.open.filter(function (x) { return x !== p; }), false, p === "news" ? false : S.live);
      else setPanels(S.open.concat([p]), S.briefing, S.live);
    } else if (name === "live") {
      setPanels(args[0] && S.open.indexOf("news") < 0 ? S.open.concat(["news"]) : S.open, S.briefing, !!args[0]);
    }
  }

  // ---- Messages from Python ------------------------------------------------------------
  function recv(messages) {
    if (!Array.isArray(messages)) messages = [messages];
    messages.forEach(function (m) {
      try {
        if (m.t === "status") setStatus(m.state, m.text, m.online);
        else if (m.t === "level") S.level = Math.max(S.level, +m.v || 0);
        else if (m.t === "line") addLine(m);
        else if (m.t === "panels") { if (m.channel && !S.channelPicked) S.channel = m.channel; setPanels(m.open || [], !!m.briefing, !!m.live); }
        else if (m.t === "data") setData(m.key, m.value);
      } catch (e) { if (window.console) console.error("ATOM.recv", m && m.t, e); }
    });
    return true;
  }

  function applySnapshot(snap) {
    if (!snap) return;
    if (snap.channel) S.channel = snap.channel;
    Object.keys(snap.data || {}).forEach(function (k) { setData(k, snap.data[k]); });
    S.lines = [];
    (snap.lines || []).forEach(addLine);
    setStatus(snap.state, snap.status, snap.online);
    setPanels(snap.open || [], !!snap.briefing, !!snap.live);
  }

  // ---- Status and the atom -------------------------------------------------------------
  function prettyStatus(text) {
    var t = String(text || "").trim();
    t = t.replace(/\.\.\.\s+/g, " · ").replace(/\.\.\.$/, "").replace(/…$/, "");
    return t.toUpperCase();
  }
  function setStatus(state, text, online) {
    S.state = state || "idle";
    S.status = text || "";
    document.body.classList.remove("idle", "listening", "thinking", "speaking", "locked");
    document.body.classList.add(S.state);
    $("status").textContent = prettyStatus(text || "Standing by");
    if (online !== undefined) {
      S.online = !!online;
      $("net").textContent = S.online ? "ONLINE" : "OFFLINE";
      $("net").classList.toggle("off", !S.online);
    }
  }

  var atom = { phase: [0, 2.1, 4.2], rot: 0, lvl: 0, t0: performance.now(), last: 0 };
  var ANG = [0, 60, -60].map(function (d) { return d * Math.PI / 180; });
  var SPEED = { idle: 0.55, listening: 1.4, thinking: 5.5, speaking: 1.9, locked: 0.3 };   // electrons, rad/s
  var SPIN = { idle: 3, listening: 8, thinking: 70, speaking: 12, locked: 0 };              // whole atom, deg/s

  function frame(now) {
    requestAnimationFrame(frame);
    if (now - atom.last < 32) return;          // ~30 fps is plenty and easy on the laptop
    var dt = Math.min(0.1, (now - (atom.last || now)) / 1000);
    atom.last = now;
    var t = (now - atom.t0) / 1000;
    var st = S.state;
    atom.lvl += ((st === "listening" ? S.level : 0) - atom.lvl) * 0.35;
    S.level *= 0.6;                            // peaks decay between updates
    var electrons = $("electrons").children;
    for (var i = 0; i < 3; i++) {
      atom.phase[i] += (SPEED[st] || 0.55) * (1 + atom.lvl * 1.5) * dt;
      var x = 100 * Math.cos(atom.phase[i]), y = 36 * Math.sin(atom.phase[i]);
      var c = Math.cos(ANG[i]), s = Math.sin(ANG[i]);
      electrons[i].setAttribute("cx", (x * c - y * s).toFixed(2));
      electrons[i].setAttribute("cy", (x * s + y * c).toFixed(2));
    }
    atom.rot = (atom.rot + (SPIN[st] || 0) * dt) % 360;
    var scale = 1, glowR = 30 + 3 * Math.sin(t * 1.5), coreR = 12, blur = 3;
    if (st === "listening") {
      scale = 1 + 0.22 * atom.lvl; glowR = 32 + 26 * atom.lvl; coreR = 12 + 5 * atom.lvl; blur = 3 + 5 * atom.lvl;
    } else if (st === "speaking") {
      var pulse = 0.5 + 0.5 * Math.abs(Math.sin(t * 7)) * Math.abs(Math.sin(t * 2.3));
      glowR = 30 + 18 * pulse; coreR = 11 + 6 * pulse; blur = 3 + 2 * pulse;
    } else if (st === "thinking") {
      glowR = 30 + 5 * Math.sin(t * 6); blur = 3.5;
    }
    $("spin").setAttribute("transform", "rotate(" + atom.rot.toFixed(2) + ") scale(" + scale.toFixed(3) + ")");
    $("halo").setAttribute("transform", "rotate(" + (-atom.rot * 0.5).toFixed(2) + ")");
    $("nucGlow").setAttribute("r", glowR.toFixed(2));
    $("nucCore").setAttribute("r", coreR.toFixed(2));
    $("glowBlur").setAttribute("stdDeviation", blur.toFixed(2));
  }

  // ---- Panels --------------------------------------------------------------------------
  function setPanels(open, briefing, live) {
    var before = S.open.slice();
    S.open = ORDER.filter(function (p) { return open.indexOf(p) >= 0; });
    S.briefing = briefing && BRIEFING.every(function (p) { return S.open.indexOf(p) >= 0; });
    S.live = live && S.open.indexOf("news") >= 0;
    layout(before);
    renderVideo();
    renderChatTitle();
    document.querySelectorAll("[data-dock]").forEach(function (b) {
      var name = b.getAttribute("data-dock");
      b.classList.toggle("on", name === "core" ? S.open.length === 0 : S.open.indexOf(name) >= 0);
    });
    document.body.classList.toggle("docked", S.open.length > 0);
    if (S.open.indexOf("markets") >= 0) setTimeout(renderChart, 650);
  }

  function layout(before) {
    var n = S.open.length;
    var rects = n === 1 && SMALL_ALONE[S.open[0]] ? [SMALL_ALONE[S.open[0]]] : (LAYOUTS[n] || []);
    var fresh = 0;
    document.querySelectorAll(".panel").forEach(function (el) {
      var name = el.getAttribute("data-panel");
      var i = S.open.indexOf(name);
      if (i < 0) { el.classList.remove("open"); return; }
      var r = rects[i].slice();
      if (MAX_HEIGHT[name] && r[3] > MAX_HEIGHT[name] && n > 1) r[3] = MAX_HEIGHT[name];
      var wasOpen = before.indexOf(name) >= 0;
      if (!wasOpen) {  // jump to the new spot without sliding, then fly in
        el.style.transition = "none";
        place(el, r);
        void el.offsetWidth;
        el.style.transition = "";
        el.style.setProperty("--delay", (fresh++ * 0.08) + "s");
      } else {
        place(el, r);
      }
      el.classList.add("open");
    });
  }
  function place(el, r) {
    el.style.left = r[0] + "%"; el.style.top = r[1] + "%";
    el.style.width = r[2] + "%"; el.style.height = r[3] + "%";
  }

  // ---- Data ----------------------------------------------------------------------------
  function setData(key, value) {
    S.data[key] = value;
    if (key === "ticker") renderTicker();
    else if (key === "weather") renderWeather();
    else if (key === "battery") renderBattery();
    else if (key === "news") renderNews();
    else if (key === "fx") renderChart();
    else if (key === "music") renderMusic();
    else if (key === "inbox") { renderInbox(); renderToday(); }
    else if (key === "reminders") renderToday();
  }

  function renderTicker() {
    var d = S.data.ticker || {};
    var parts = [];
    if (d.usd_ngn) parts.push("USD/NGN <b>" + fmt(d.usd_ngn) + "</b>" + pct(d.usd_ngn_change, true));
    if (d.btc) parts.push("BTC <b>$" + fmt(d.btc) + "</b>" + pct(d.btc_change));
    if (d.eth) parts.push("ETH <b>$" + fmt(d.eth) + "</b>" + pct(d.eth_change));
    if (d.gold) parts.push("GOLD <b>$" + fmt(d.gold) + "</b>" + pct(d.gold_change));
    $("ticker").innerHTML = parts.map(function (p) { return "<span>" + p + "</span>"; }).join("");
    if (d.usd_ngn) $("fxNow").textContent = "₦" + fmt(d.usd_ngn);
    renderStats();
  }
  function renderWeather() {
    var w = S.data.weather;
    $("weather").textContent = w ? (String(w.city || "").toUpperCase() + " " + w.temp + "°C") : "";
    $("weather").title = w ? (w.text + ", " + w.rain + "% chance of rain") : "";
  }
  function renderBattery() {
    var b = S.data.battery;
    $("battery").textContent = b && b.percent != null ? "BATTERY " + b.percent + "%" + (b.plugged ? " ⚡" : "") : "";
  }

  function renderNews() {
    var items = S.data.news || [];
    if (!items.length) { $("headlines").innerHTML = '<li class="muted">No headlines right now.</li>'; return; }
    $("headlines").innerHTML = items.map(function (h) {
      return "<li>" + esc(h.title) + ' <span class="src">— ' + esc(h.source) + (h.age ? " · " + esc(h.age) : "") + "</span></li>";
    }).join("");
    $("breakingText").textContent = items.slice(0, 2).map(function (h) { return h.title; }).join("  ·  ");
    var sources = {};
    items.forEach(function (h) { sources[h.source] = 1; });
    $("newsCount").textContent = "// " + Object.keys(sources).length + " SOURCES";
  }

  function renderVideo() {
    var body = document.querySelector(".news-body");
    var box = $("video");
    var frame = box.querySelector("iframe");
    var ch = S.channel || DEFAULT_CHANNEL;
    $("channelBtn").textContent = ch.name;
    $("videoLabel").textContent = "LIVE · " + ch.name;
    $("newsTitle").textContent = "NEWS // " + (S.live ? ch.name + " LIVE" : "HEADLINES");
    $("liveBtn").classList.toggle("on", S.live);
    body.classList.toggle("live", S.live);
    if (S.live) {
      var src = "https://www.youtube.com/embed/live_stream?channel=" + encodeURIComponent(ch.id) +
                "&autoplay=1&rel=0&modestbranding=1" + (S.liveByClick ? "" : "&mute=1");
      if (!frame || frame.getAttribute("data-ch") !== ch.id) {
        if (frame) frame.remove();
        frame = document.createElement("iframe");
        frame.setAttribute("data-ch", ch.id);
        frame.setAttribute("allow", "autoplay; encrypted-media; picture-in-picture");
        frame.setAttribute("allowfullscreen", "");
        frame.src = src;
        box.appendChild(frame);
      }
    } else if (frame) {
      frame.remove();          // stop streaming when not wanted
    }
    S.liveByClick = false;
  }

  function renderChart() {
    var host = $("chart");
    var pts = (S.data.fx || []).map(function (p) { return [p[0], +p[1]]; });
    var t = S.data.ticker || {};
    var today = new Date().toISOString().slice(0, 10);
    if (t.usd_ngn && (!pts.length || pts[pts.length - 1][0] < today)) pts.push([today, t.usd_ngn]);
    if (pts.length < 2) { host.innerHTML = '<div class="muted">' + (pts.length ? "Rate history coming soon." : "Loading rates…") + "</div>"; return; }
    var vals = pts.map(function (p) { return p[1]; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = (hi - lo) * 0.15 || 1;
    lo -= pad; hi += pad;
    var W = 1000, H = 300;
    var xy = pts.map(function (p, i) {
      return [(i / (pts.length - 1)) * W, H - ((p[1] - lo) / (hi - lo)) * H];
    });
    var line = xy.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var area = line + " L" + W + " " + H + " L0 " + H + " Z";
    var last = xy[xy.length - 1];
    host.innerHTML =
      '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none">' +
      '<defs><linearGradient id="fxg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#00e5ff" stop-opacity=".35"/>' +
      '<stop offset="1" stop-color="#00e5ff" stop-opacity="0"/></linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#fxg)" stroke="none"/>' +
      '<path d="' + line + '" fill="none" stroke="#00e5ff" stroke-width="2" vector-effect="non-scaling-stroke"/>' +
      '<circle cx="' + last[0] + '" cy="' + last[1].toFixed(1) + '" r="4" fill="#e8fdff" vector-effect="non-scaling-stroke"/>' +
      "</svg>" +
      '<span class="lbl" style="top:0;right:4px">₦' + fmt(Math.max.apply(null, vals)) + "</span>" +
      '<span class="lbl" style="bottom:0;right:4px">₦' + fmt(Math.min.apply(null, vals)) + "</span>" +
      '<span class="lbl" style="bottom:0;left:2px">' + esc(pts[0][0].slice(5)) + "</span>";
    var change = (vals[vals.length - 1] / vals[0] - 1) * 100;
    host.setAttribute("data-change", change.toFixed(2));
    renderStats(change);
  }
  function renderStats(change) {
    var t = S.data.ticker || {};
    if (change === undefined) {
      var c = $("chart").getAttribute("data-change");
      change = c == null ? null : +c;
    }
    var parts = [];
    if (change != null) parts.push("30D" + pct(change, true));
    if (t.btc) parts.push("BTC <b>$" + fmt(t.btc) + "</b>");
    if (t.eth) parts.push("ETH <b>$" + fmt(t.eth) + "</b>");
    if (t.gold) parts.push("GOLD <b>$" + fmt(t.gold) + "</b>");
    $("stats").innerHTML = parts.map(function (p) { return "<span>" + p + "</span>"; }).join("");
  }

  function addLine(m) {
    S.lines.push(m);
    if (S.lines.length > 20) S.lines = S.lines.slice(-20);
    var who = String(m.who || "");
    $("chat").innerHTML = S.lines.map(function (l) {
      var cls = l.who === "You" ? "you" : l.who === "ATOM" ? "atom" : "sys";
      return '<div class="ln ' + cls + '"><span class="who">' + esc(String(l.who).toUpperCase()) + "</span>" + esc(l.text) + "</div>";
    }).join("");
    $("chatTime").textContent = m.at || "";
    $("chat").scrollTop = $("chat").scrollHeight;
    return who;
  }
  function renderChatTitle() {
    var h = new Date().getHours();
    var part = h < 12 ? "MORNING" : h < 17 ? "AFTERNOON" : "EVENING";
    $("chatTitle").textContent = S.briefing ? "ATOM // " + part + " BRIEFING" : "ATOM // TRANSCRIPT";
  }

  function renderMusic() {
    var m = S.data.music || {};
    $("musicNote").textContent = m.error || "";
    $("musicTitle").textContent = m.title || "Nothing playing";
    $("musicArtist").textContent = m.title ? (m.artist || "") : 'Say "play some afrobeats"';
    $("musicApp").textContent = (m.app || "").toUpperCase();
    $("eq").classList.toggle("on", !!m.playing);
  }

  function renderInbox() {
    var d = S.data.inbox || {};
    var items = d.items || [];
    $("inboxCount").textContent = items.length;
    if (!items.length) {
      var note = d.status && d.status !== "on" ? " (notifications: " + d.status + ")" : "";
      $("inbox").innerHTML = '<li class="muted">No new messages.' + esc(note) + "</li>";
      return;
    }
    $("inbox").innerHTML = items.map(function (n) {
      return '<li><span class="from">' + esc(n.app) + " · " + esc(n.sender) + '</span> <span class="age">' + esc(n.age) +
             "</span><div class=\"msg\">" + esc(n.text) + "</div></li>";
    }).join("");
  }

  function renderToday() {
    var rem = S.data.reminders || [];
    var inbox = (S.data.inbox || {}).items || [];
    var rows = rem.map(function (r) {
      return '<li>⏰ <span class="when">' + esc(r.when) + "</span> " + esc(r.text) + "</li>";
    });
    var bySender = {};
    var senders = [];
    inbox.forEach(function (n) {
      var key = n.app + " · " + n.sender;
      if (!bySender[key]) { bySender[key] = 0; senders.push(key); }
      bySender[key]++;
    });
    senders.slice(0, 2).forEach(function (k) {
      rows.push('<li><span class="dot">●</span> ' + esc(k) + " · " + bySender[k] + " new</li>");
    });
    $("remCount").textContent = rem.length;
    $("today").innerHTML = rows.length ? rows.join("") : '<li class="muted">Nothing on today.</li>';
  }

  // ---- Clock, input, start-up ----------------------------------------------------------
  function tick() {
    var d = new Date();
    var time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    var day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }).replace(",", "");
    $("clock").textContent = time + " · " + day.toUpperCase();
  }

  function wire() {
    document.querySelectorAll("[data-dock]").forEach(function (b) {
      b.addEventListener("click", function () { call("toggle", b.getAttribute("data-dock")); });
    });
    document.querySelectorAll("[data-media]").forEach(function (b) {
      b.addEventListener("click", function () { call("media", b.getAttribute("data-media")); });
    });
    $("atom").addEventListener("click", function () { call("talk"); });
    $("stopBtn").addEventListener("click", function (e) { e.stopPropagation(); call("stop"); });
    $("playBtn").addEventListener("click", function () { S.liveByClick = true; call("live", true); if (!api()) renderVideo(); });
    $("liveBtn").addEventListener("click", function () { S.liveByClick = !S.live; call("live", !S.live); });
    $("channelBtn").addEventListener("click", function () {
      var i = CHANNELS.findIndex(function (c) { return c.id === (S.channel || {}).id; });
      S.channel = CHANNELS[(i + 1) % CHANNELS.length];
      S.channelPicked = true;
      var wasLive = S.live;
      S.live = false; renderVideo(); S.live = wasLive; S.liveByClick = true; renderVideo();
    });
    document.addEventListener("keydown", function (e) {
      if (e.code === "Space") { e.preventDefault(); call("talk"); }
      else if (e.code === "Escape") call("stop");
    });
    window.addEventListener("resize", function () { if (S.open.indexOf("markets") >= 0) renderChart(); });
  }

  function connect() {
    var a = api();
    if (!a || !a.ready) return;
    try {
      var p = a.ready();
      if (p && p.then) p.then(applySnapshot);
    } catch (e) { /* the sender thread will still push updates */ }
  }

  window.ATOM = { recv: recv, state: S, applySnapshot: applySnapshot, setPanels: setPanels };
  wire();
  tick();
  setInterval(tick, 1000);
  renderChatTitle();
  setInterval(renderChatTitle, 60000);
  requestAnimationFrame(frame);
  window.addEventListener("pywebviewready", connect);
  if (api()) connect();
})();
