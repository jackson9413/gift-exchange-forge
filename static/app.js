/* Gift Exchange Forge - front end. Vanilla JS, no build step. */

var STATE = { exchanges: [], current: null, samples: [] };

function $(id) { return document.getElementById(id); }

function toast(message, isError) {
  var el = $("toast");
  el.textContent = message;
  el.className = "toast" + (isError ? " error-toast" : "");
  window.setTimeout(function () { el.className = "toast hidden"; }, 3200);
}

function api(method, url, body) {
  var opts = { method: method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined && body !== null) { opts.body = JSON.stringify(body); }
  return fetch(url, opts).then(function (res) {
    return res.text().then(function (text) {
      var data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (e) { data = { error: text }; }
      if (!res.ok) { throw new Error(data.error || ("request failed: " + res.status)); }
      return data;
    });
  });
}

function esc(value) {
  if (value === null || value === undefined) { return ""; }
  return String(value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function money(value) {
  if (value === null || value === undefined || value === "") { return "-"; }
  var n = Number(value);
  if (isNaN(n)) { return String(value); }
  return "$" + n.toFixed(2);
}

function fmtDate(value) {
  if (!value) { return "not set"; }
  var parts = String(value).split("-");
  if (parts.length !== 3) { return value; }
  var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var month = months[Number(parts[1]) - 1] || parts[1];
  return parts[2] + " " + month + " " + parts[0];
}

function initTabs() {
  var tabs = document.querySelectorAll(".tab");
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      Array.prototype.forEach.call(tabs, function (t) { t.classList.remove("active"); });
      var panels = document.querySelectorAll(".panel");
      Array.prototype.forEach.call(panels, function (p) { p.classList.remove("active"); });
      tab.classList.add("active");
      var target = $(tab.getAttribute("data-panel"));
      if (target) { target.classList.add("active"); }
    });
  });
}

function loadExchanges(selectId) {
  return api("GET", "/api/exchanges").then(function (data) {
    STATE.exchanges = data.exchanges || [];
    var select = $("exchange-select");
    select.innerHTML = "";
    if (!STATE.exchanges.length) {
      var opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No exchange yet";
      select.appendChild(opt);
      return null;
    }
    STATE.exchanges.forEach(function (ex) {
      var opt = document.createElement("option");
      opt.value = ex.id;
      opt.textContent = ex.name + " (" + ex.participants + ")";
      select.appendChild(opt);
    });
    if (selectId) { select.value = selectId; }
    if (!select.value) { select.value = STATE.exchanges[0].id; }
    return select.value;
  });
}

function openExchange(id) {
  if (!id) { return Promise.resolve(null); }
  return api("GET", "/api/exchanges/" + encodeURIComponent(id)).then(function (data) {
    STATE.current = data;
    $("exchange-select").value = id;
    renderAll();
    return data;
  });
}

function refresh() {
  var keep = STATE.current ? STATE.current.exchange.id : null;
  return loadExchanges(keep).then(function (id) {
    if (id) { return openExchange(id); }
    return null;
  });
}

function renderAll() {
  if (!STATE.current) { return; }
  renderSettings();
  renderParticipants();
  renderExclusions();
  renderAssignment();
  renderReadiness();
  renderCalendar();
}

function renderSettings() {
  var ex = STATE.current.exchange;
  $("set-name").value = ex.name || "";
  $("set-budget").value = (ex.budget === null || ex.budget === undefined) ? "" : ex.budget;
  $("set-draw").value = ex.draw_date || "";
  $("set-shopping").value = ex.shopping_deadline || "";
  $("set-exchange").value = ex.exchange_date || "";
  $("set-shipping").value = (ex.shipping_days === null) ? "" : ex.shipping_days;
  $("set-circle").value = ex.circle || "";
  $("set-notes").value = ex.notes || "";
  $("rule-household").checked = !!ex.no_same_household;
  $("rule-group").checked = !!ex.no_same_group;
  $("rule-repeats").checked = !!ex.avoid_repeats;
  $("rule-reveal").checked = !!ex.allow_reveal_early;
}

var CODE_OPEN = "<code>";
var CODE_CLOSE = "<" + "code>";

function renderParticipants() {
  var body = $("participants-body");
  body.innerHTML = "";
  var people = STATE.current.exchange.participants || [];
  people.forEach(function (p) {
    var tr = document.createElement("tr");
    var wishCount = (p.wishes || []).length;
    var codeCell = CODE_OPEN + esc(p.access_code || "-") + CODE_CLOSE;
    var actions = "<button class='link' data-edit='" + p.id + "'>edit</button>" +
      " <button class='link danger' data-del='" + p.id + "'>remove</button>";
    tr.innerHTML =
      "<td>" + esc(p.name) + (wishCount ? " <span class='muted'>(" + wishCount + ")</span>" : "") + "</td>" +
      "<td>" + esc(p.email || "-") + "</td>" +
      "<td>" + esc(p.household || "-") + "</td>" +
      "<td>" + codeCell + "</td>" +
      "<td>" + actions + "</td>";
    body.appendChild(tr);
  });
  Array.prototype.forEach.call(body.querySelectorAll("[data-edit]"), function (btn) {
    btn.addEventListener("click", function () { startEdit(btn.getAttribute("data-edit")); });
  });
  Array.prototype.forEach.call(body.querySelectorAll("[data-del]"), function (btn) {
    btn.addEventListener("click", function () { removeParticipant(btn.getAttribute("data-del")); });
  });
  fillPersonSelects();
}

function renderExclusions() {
  var list = $("exclusions-list");
  list.innerHTML = "";
  var ex = STATE.current.exchange;
  var pmap = {};
  (ex.participants || []).forEach(function (p) { pmap[p.id] = p; });
  (ex.exclusions || []).forEach(function (pair) {
    var a = pmap[pair[0]] ? pmap[pair[0]].name : pair[0];
    var b = pmap[pair[1]] ? pmap[pair[1]].name : pair[1];
    var li = document.createElement("li");
    li.innerHTML = esc(a) + " does not draw " + esc(b) +
      " <button class='link danger' data-unexclude='" + pair[0] + "|" + pair[1] + "'>undo</button>";
    list.appendChild(li);
  });
  Array.prototype.forEach.call(list.querySelectorAll("[data-unexclude]"), function (btn) {
    btn.addEventListener("click", function () {
      var bits = btn.getAttribute("data-unexclude").split("|");
      removeExclusion(bits[0], bits[1]);
    });
  });
}

function fillPersonSelects() {
  var people = STATE.current ? (STATE.current.exchange.participants || []) : [];
  ["x-a", "x-b"].forEach(function (id) {
    var select = $(id);
    var previous = select.value;
    select.innerHTML = "";
    people.forEach(function (p) {
      var opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
    if (previous) { select.value = previous; }
  });
}

function startEdit(pid) {
  var people = STATE.current.exchange.participants || [];
  var found = null;
  people.forEach(function (p) { if (p.id === pid) { found = p; } });
  if (!found) { return; }
  $("edit-participant-form").classList.remove("hidden");
  $("e-id").value = found.id;
  $("e-name").value = found.name || "";
  $("e-email").value = found.email || "";
  $("e-household").value = found.household || "";
  $("e-groups").value = (found.groups || []).join(", ");
  $("e-code").value = found.access_code || "";
  $("e-notes").value = found.notes || "";
  $("e-wishes").value = (found.wishes || []).map(function (w) {
    var price = (w.price === null || w.price === undefined) ? "" : w.price;
    return [w.item, price, w.note || ""].join(" | ");
  }).join("\n");
  var bought = [];
  Object.keys(found.purchased || {}).forEach(function (k) { bought.push(k + " | " + found.purchased[k]); });
  $("e-purchased").value = bought.join("\n");
}

function parseLines(text) {
  return String(text || "").split("\n").map(function (line) { return line.trim(); })
    .filter(function (line) { return line.length > 0; });
}

function removeParticipant(pid) {
  if (!STATE.current) { return; }
  api("DELETE", "/api/exchanges/" + encodeURIComponent(STATE.current.exchange.id) +
      "/participants/" + encodeURIComponent(pid)).then(function (data) {
    STATE.current = data;
    renderAll();
    toast("Person removed");
  }).catch(function (err) { toast(err.message, true); });
}

function removeExclusion(a, b) {
  if (!STATE.current) { return; }
  api("DELETE", "/api/exchanges/" + encodeURIComponent(STATE.current.exchange.id) +
      "/exclude?a=" + encodeURIComponent(a) + "&b=" + encodeURIComponent(b)).then(function (data) {
    STATE.current = data;
    renderAll();
  }).catch(function (err) { toast(err.message, true); });
}

function renderAssignment() {
  var body = $("assignment-body");
  body.innerHTML = "";
  var data = STATE.current;
  var ex = data.exchange;
  var assignment = data.assignment || {};
  var pmap = {};
  (ex.participants || []).forEach(function (p) { pmap[p.id] = p; });
  var entries = Object.keys(assignment).map(function (gid) {
    return { giver: gid, receiver: assignment[gid] };
  });
  entries.sort(function (a, b) {
    var an = pmap[a.giver] ? pmap[a.giver].name : a.giver;
    var bn = pmap[b.giver] ? pmap[b.giver].name : b.giver;
    return an.localeCompare(bn);
  });
  if (!entries.length) {
    $("draw-status").innerHTML = "<span class='muted'>No draw yet. Press 'Run the draw'.</span>";
    return;
  }
  $("draw-status").innerHTML = "<span class='ok'>" + entries.length + " pairings drawn. Every participant gives to exactly one person.</span>";
  entries.forEach(function (e) {
    var giver = pmap[e.giver];
    var receiver = pmap[e.receiver];
    var wishes = receiver ? (receiver.wishes || []).length : 0;
    var tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + esc(giver ? giver.name : e.giver) + "</td>" +
      "<td>" + esc(receiver ? receiver.name : e.receiver) + "</td>" +
      "<td>" + esc(receiver ? (receiver.household || "-") : "-") + "</td>" +
      "<td>" + (wishes ? wishes + " wish" + (wishes > 1 ? "es" : "") : "no wishlist") + "</td>";
    body.appendChild(tr);
  });
}

function renderReadiness() {
  var report = STATE.current.report || {};
  var summary = report.summary || {};
  $("score-value").textContent = (report.score === undefined ? "--" : report.score);
  $("score-value").className = "score " + (report.verdict || "");
  $("verdict-label").textContent = report.verdict_label || "No report";
  var bits = [];
  bits.push(summary.participants + " people");
  if (summary.days_to_exchange !== null && summary.days_to_exchange !== undefined) {
    bits.push(summary.days_to_exchange + " days to the exchange");
  }
  if (summary.assigned) { bits.push(summary.assigned + " pairings"); }
  if (summary.critical) { bits.push(summary.critical + " critical"); }
  if (summary.high) { bits.push(summary.high + " high"); }
  $("score-summary").textContent = bits.join(" - ");
  var axes = $("axes-list");
  axes.innerHTML = "";
  (report.axes || []).forEach(function (ax) {
    var div = document.createElement("div");
    div.className = "axis";
    div.innerHTML = "<div class='axis-head'><span>" + esc(ax.label) + "</span><span>" + ax.score + " / 100</span></div>" +
      "<div class='bar'><div class='fill' style='width:" + ax.score + "%'></div></div>";
    axes.appendChild(div);
  });
  var list = $("findings-list");
  list.innerHTML = "";
  if (!(report.findings || []).length) {
    list.innerHTML = "<p class='ok'>Nothing to fix. This exchange is ready to draw.</p>";
  }
  (report.findings || []).forEach(function (f) {
    var div = document.createElement("div");
    div.className = "finding sev-" + f.severity;
    div.innerHTML = "<div class='sev'>" + esc(f.severity) + "</div>" +
      "<div><h4>" + esc(f.title) + "</h4>" +
      "<p><b>Evidence:</b> " + esc(f.evidence) + "</p>" +
      "<p><b>Why it matters:</b> " + esc(f.why) + "</p>" +
      "<p><b>Fix:</b> " + esc(f.fix) + "</p></div>";
    list.appendChild(div);
  });
  var fixes = $("fix-list");
  fixes.innerHTML = "";
  (report.fix_plan || []).forEach(function (step) {
    var li = document.createElement("li");
    li.innerHTML = "<b>" + esc(step.title) + "</b> <span class='muted'>(" + esc(step.severity) + " - " + esc(step.axis_label) + ")</span><br>" + esc(step.fix);
    fixes.appendChild(li);
  });
}

function renderCalendar() {
  var ex = STATE.current.exchange;
  var report = STATE.current.report || {};
  var summary = report.summary || {};
  var list = $("dates-list");
  list.innerHTML = "";
  var rows = [
    ["Draw", fmtDate(ex.draw_date)],
    ["Shopping deadline", fmtDate(ex.shopping_deadline)],
    ["Exchange", fmtDate(ex.exchange_date)],
    ["Shipping buffer", (ex.shipping_days || 0) + " day(s)"],
    ["Shopping window", summary.shopping_window_days === null || summary.shopping_window_days === undefined ? "unknown" : summary.shopping_window_days + " day(s)"],
    ["Circle", ex.circle || "not set"],
    ["Budget cap", ex.budget === null || ex.budget === undefined ? "not set" : money(ex.budget)]
  ];
  rows.forEach(function (row) {
    var li = document.createElement("li");
    li.innerHTML = "<span class='muted'>" + esc(row[0]) + "</span> " + esc(row[1]);
    list.appendChild(li);
  });
  var spend = Number(summary.spend || 0);
  var cap = ex.budget;
  $("spend-total").textContent = money(spend);
  $("spend-label").textContent = spend === 0 ? "Nothing recorded" : "Recorded across " + (summary.assigned || 0) + " buyer(s)";
  if (cap !== null && cap !== undefined) {
    $("spend-cap").textContent = "Cap is " + money(cap) + " per person" + (spend > cap ? " - over" : "");
  } else {
    $("spend-cap").textContent = "No budget cap set";
  }
  var body = $("budget-body");
  body.innerHTML = "";
  (ex.participants || []).forEach(function (p) {
    var bought = p.purchased || {};
    Object.keys(bought).forEach(function (gift) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(p.name) + "</td><td>" + esc(gift) + "</td><td>" + money(bought[gift]) + "</td>";
      body.appendChild(tr);
    });
  });
  var id = encodeURIComponent(ex.id);
  $("export-md").href = "/api/exchanges/" + id + "/export?format=md";
  $("export-csv").href = "/api/exchanges/" + id + "/export?format=csv";
  $("export-ics").href = "/api/exchanges/" + id + "/export?format=ics";
  $("export-json").href = "/api/exchanges/" + id + "/export?format=json";
  $("export-sheet").href = "/api/exchanges/" + id + "/export?format=sheet";
}

function currentId() {
  return STATE.current ? STATE.current.exchange.id : "";
}

function applyResult(data, message) {
  if (data && data.exchange) {
    STATE.current = data;
    renderAll();
  }
  if (message) { toast(message); }
}

function initForms() {
  $("exchange-select").addEventListener("change", function () {
    openExchange(this.value);
  });

  $("settings-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!currentId()) { toast("Create an exchange first", true); return; }
    var body = {
      name: $("set-name").value,
      budget: $("set-budget").value === "" ? null : $("set-budget").value,
      draw_date: $("set-draw").value || null,
      shopping_deadline: $("set-shopping").value || null,
      exchange_date: $("set-exchange").value || null,
      shipping_days: $("set-shipping").value,
      circle: $("set-circle").value,
      notes: $("set-notes").value,
      no_same_household: $("rule-household").checked,
      no_same_group: $("rule-group").checked,
      avoid_repeats: $("rule-repeats").checked,
      allow_reveal_early: $("rule-reveal").checked
    };
    api("PUT", "/api/exchanges/" + encodeURIComponent(currentId()), body)
      .then(function (data) { applyResult(data, "Settings saved"); })
      .catch(function (err) { toast(err.message, true); });
  });

  $("participant-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!currentId()) { toast("Create an exchange first", true); return; }
    var body = {
      name: $("p-name").value,
      email: $("p-email").value,
      household: $("p-household").value,
      groups: $("p-groups").value ? $("p-groups").value.split(",").map(function (g) { return g.trim(); }) : []
    };
    api("POST", "/api/exchanges/" + encodeURIComponent(currentId()) + "/participants", body)
      .then(function (data) {
        $("p-name").value = ""; $("p-email").value = ""; $("p-household").value = ""; $("p-groups").value = "";
        applyResult(data, "Added " + body.name);
      })
      .catch(function (err) { toast(err.message, true); });
  });

  $("edit-participant-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var pid = $("e-id").value;
    if (!pid || !currentId()) { return; }
    var wishes = parseLines($("e-wishes").value).map(function (line) {
      var bits = line.split("|").map(function (b) { return b.trim(); });
      return { item: bits[0] || "", price: bits.length > 1 && bits[1] !== "" ? Number(bits[1]) : null, note: bits.length > 2 ? bits[2] : "" };
    });
    var purchased = {};
    parseLines($("e-purchased").value).forEach(function (line) {
      var bits = line.split("|").map(function (b) { return b.trim(); });
      if (bits[0]) { purchased[bits[0]] = bits.length > 1 ? Number(bits[1]) : 0; }
    });
    var body = {
      name: $("e-name").value,
      email: $("e-email").value,
      household: $("e-household").value,
      groups: $("e-groups").value ? $("e-groups").value.split(",").map(function (g) { return g.trim(); }) : [],
      access_code: $("e-code").value,
      notes: $("e-notes").value,
      wishes: wishes,
      purchased: purchased
    };
    api("PATCH", "/api/exchanges/" + encodeURIComponent(currentId()) + "/participants/" + encodeURIComponent(pid), body)
      .then(function (data) {
        $("edit-participant-form").classList.add("hidden");
        applyResult(data, "Saved");
      })
      .catch(function (err) { toast(err.message, true); });
  });

  $("btn-cancel-edit").addEventListener("click", function () {
    $("edit-participant-form").classList.add("hidden");
  });

  $("exclude-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!currentId()) { return; }
    api("POST", "/api/exchanges/" + encodeURIComponent(currentId()) + "/exclude",
        { a: $("x-a").value, b: $("x-b").value })
      .then(function (data) { applyResult(data, "Exclusion added"); })
      .catch(function (err) { toast(err.message, true); });
  });

    function runDraw() {
    if (!currentId()) { toast("Create an exchange first", true); return; }
    $("draw-status").innerHTML = "<span class='muted'>Drawing...</span>";
    api("POST", "/api/exchanges/" + encodeURIComponent(currentId()) + "/draw", {})
      .then(function (data) {
        if (data.assignment && Object.keys(data.assignment).length) {
          STATE.current.assignment = data.assignment;
        }
        STATE.current.report = data.report;
        renderAssignment();
        renderReadiness();
        if (data.ok) {
          toast("Draw complete - " + Object.keys(data.assignment).length + " pairings");
        } else {
          $("draw-status").innerHTML = "<span class='bad'>No valid draw. See the findings in Readiness.</span>";
          toast("No valid draw under the current rules", true);
        }
      })
      .catch(function (err) { toast(err.message, true); });
  }

  $("btn-run-draw").addEventListener("click", runDraw);
  $("btn-redraw").addEventListener("click", runDraw);

  $("run-form").addEventListener("submit", function (event) {
    event.preventDefault();
    if (!currentId()) { return; }
    api("POST", "/api/exchanges/" + encodeURIComponent(currentId()) + "/runs",
        { rating: $("run-rating").value, notes: $("run-notes").value })
      .then(function (data) {
        $("run-message").textContent = "Saved run " + data.run_id + " at " + data.report.score + "/100.";
        toast("Run logged");
      })
      .catch(function (err) { toast(err.message, true); });
  });

  $("reveal-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var code = $("reveal-code").value.trim().toUpperCase();
    if (!code) { return; }
    api("GET", "/api/reveal?code=" + encodeURIComponent(code))
      .then(function (data) {
        var html = "<div class='reveal'><h3>" + esc(data.you) + " draws " + esc(data.drawn || "nobody yet") + "</h3>";
        html += "<p class='muted'>" + esc(data.exchange.name) + "</p>";
        html += "<ul class='plain'>";
        html += "<li>Draw date: " + esc(fmtDate(data.exchange.draw_date)) + "</li>";
        html += "<li>Buy by: " + esc(fmtDate(data.exchange.shopping_deadline)) + "</li>";
        html += "<li>Exchange: " + esc(fmtDate(data.exchange.exchange_date)) + "</li>";
        html += "<li>Budget: " + esc(money(data.exchange.budget)) + "</li>";
        html += "</ul>";
        if ((data.wishes || []).length) {
          html += "<h4>What they asked for</h4><ul>";
          data.wishes.forEach(function (w) {
            html += "<li>" + esc(w.item) + (w.price ? " (" + esc(money(w.price)) + ")" : "") + (w.note ? " - " + esc(w.note) : "") + "</li>";
          });
          html += "</ul>";
        }
        html += "</div>";
        $("reveal-result").innerHTML = html;
      })
      .catch(function (err) {
        $("reveal-result").innerHTML = "<span class='bad'>" + esc(err.message) + "</span>";
      });
  });

  $("btn-new").addEventListener("click", function () {
    $("new-modal").classList.remove("hidden");
  });
  $("btn-close-new").addEventListener("click", function () {
    $("new-modal").classList.add("hidden");
  });
  $("btn-create-brief").addEventListener("click", function () {
    var brief = $("brief-input").value;
    if (!brief.trim()) { $("brief-error").textContent = "Paste a brief first."; return; }
    api("POST", "/api/exchanges", { brief: brief })
      .then(function (data) {
        $("new-modal").classList.add("hidden");
        $("brief-error").textContent = "";
        refresh().then(function () {
          openExchange(data.exchange.id).then(function () { toast("Exchange created"); });
        });
      })
      .catch(function (err) { $("brief-error").textContent = err.message; });
  });

  $("btn-samples").addEventListener("click", function () {
    api("GET", "/api/samples").then(function (data) {
      STATE.samples = data.samples || [];
      var wrap = $("sample-list");
      wrap.innerHTML = "";
      STATE.samples.forEach(function (s) {
        var card = document.createElement("div");
        card.className = "sample-card";
        card.innerHTML = "<h4>" + esc(s.title) + "</h4><p class='muted'>" + esc(s.summary) + "</p>" +
          "<button class='btn' data-sample='" + esc(s.id) + "'>Load this sample</button>";
        wrap.appendChild(card);
      });
      Array.prototype.forEach.call(wrap.querySelectorAll("[data-sample]"), function (btn) {
        btn.addEventListener("click", function () {
          api("POST", "/api/samples/load", { sample: btn.getAttribute("data-sample") })
            .then(function (data) {
              $("sample-modal").classList.add("hidden");
              refresh().then(function () {
                openExchange(data.exchange.id).then(function () { toast("Sample loaded"); });
              });
            })
            .catch(function (err) { toast(err.message, true); });
        });
      });
      $("sample-modal").classList.remove("hidden");
    });
  });
  $("btn-close-samples").addEventListener("click", function () {
    $("sample-modal").classList.add("hidden");
  });
}

document.addEventListener("DOMContentLoaded", function () {
  initTabs();
  initForms();
  refresh();
});
