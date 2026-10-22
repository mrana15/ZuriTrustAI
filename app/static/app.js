// ZuriTrustAI web client - vanilla JS, no external libraries (works on slow connections).
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function sessionId() {
    var key = "zuri_sid", sid = null;
    try { sid = sessionStorage.getItem(key); } catch (e) {}
    if (!sid) {
      sid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now();
      try { sessionStorage.setItem(key, sid); } catch (e) {}
    }
    return sid;
  }

  function api(path, body) {
    var opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || "Request failed"); return j; });
    });
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;   // textContent only: no HTML injection
    return n;
  }

  // ---- tabs
  var tabs = document.querySelectorAll("nav button");
  tabs.forEach(function (b) {
    b.addEventListener("click", function () {
      tabs.forEach(function (x) { x.setAttribute("aria-selected", x === b ? "true" : "false"); });
      document.querySelectorAll(".panel").forEach(function (p) { p.hidden = p.id !== b.dataset.tab; });
    });
  });

  // ---- chat
  var log = $("log");
  function say(text, cls) { var m = el("div", "m " + cls, text); log.appendChild(m); log.scrollTop = log.scrollHeight; }
  function send(text) {
    say(text, "me");
    api("/api/chat", { session_id: sessionId(), message: text })
      .then(function (r) { say(r.reply, "bot" + (r.triage && r.triage.is_danger ? " " + r.triage.level : "")); })
      .catch(function (e) { say("Sorry, something went wrong: " + e.message, "bot"); });
  }
  $("chatForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var v = $("msg").value.trim();
    if (v) { send(v); $("msg").value = ""; }
  });
  send("menu");

  // ---- symptom checklist
  api("/api/danger-signs").then(function (d) {
    var box = $("signs");
    d.signs.forEach(function (s) {
      var l = el("label"), c = el("input");
      c.type = "checkbox"; c.value = s.id;
      l.appendChild(c); l.appendChild(document.createTextNode(s.label));
      box.appendChild(l);
    });
  });
  $("checkForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var ids = Array.prototype.map.call(document.querySelectorAll("#signs input:checked"), function (c) { return c.value; });
    var out = $("checkResult"); out.textContent = "";
    var p = ids.length ? api("/api/screen", { sign_ids: ids }) : api("/api/screen", { text: "none" });
    p.then(function (r) {
      var box = el("div", "result " + r.level);
      box.appendChild(el("strong", null, r.level === "emergency" ? "Go to a hospital now" : r.level === "urgent" ? "Get checked today" : "No danger sign selected"));
      box.appendChild(el("p", null, r.advice));
      box.appendChild(el("p", "small", r.disclaimer));
      out.appendChild(box);
      if (r.is_danger) { $("lvl").value = r.referral_level; }
    }).catch(function (e2) { out.textContent = e2.message; });
  });

  // ---- facilities
  api("/api/facilities").then(function (d) {
    var sel = $("state");
    d.states.forEach(function (s) { var o = el("option", null, s); o.value = s; sel.appendChild(o); });
    $("careNote").textContent = d.note;
  });
  $("careForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = "?state=" + encodeURIComponent($("state").value) + "&level=" + encodeURIComponent($("lvl").value);
    api("/api/facilities" + q).then(function (d) {
      var out = $("careResult"); out.textContent = "";
      if (!d.facilities.length) { out.appendChild(el("p", null, "No facilities found. In an emergency call 112.")); return; }
      d.facilities.forEach(function (f) {
        var c = el("div", "fac");
        c.appendChild(el("strong", null, f.name));
        c.appendChild(el("div", "small", f.area + ", " + f.state + " - " + f.hours + " - " + f.level));
        c.appendChild(el("div", null, "Tel: " + f.phone));
        c.appendChild(el("div", "small", f.services.join(", ")));
        out.appendChild(c);
      });
    });
  });
})();
