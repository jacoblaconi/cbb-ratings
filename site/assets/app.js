"use strict";
(function () {
  const PAGES = [
    ["index.html", "Ratings", "ratings"],
    ["netplus.html", "NET+", "netplus"],
    ["games.html", "Games", "games"],
    ["about.html", "Method", "about"],
  ];
  const cache = {};
  const get = (p) => (cache[p] = cache[p] || fetch("data/" + p).then((r) => {
    if (!r.ok) throw new Error(p + " " + r.status);
    return r.json();
  }));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = (x) => (x == null ? "" : Number(x).toFixed(1));
  const f2 = (x) => (x == null ? "" : Number(x).toFixed(2));
  const sgn = (x, d = 1) => (x == null ? "" : (x > 0 ? "+" : "") + Number(x).toFixed(d));
  const rk = (r) => (r == null ? "" : `<span class="rk">${Math.round(r)}</span>`);
  const teamLink = (id, name, logo) =>
    `<a href="team.html?id=${id}">${logo ? `<img src="${esc(logo)}" alt="" loading="lazy" onerror="this.remove()">` : ""}${esc(name)}</a>`;
  const qBadge = (q) => (q ? `<span class="q q${q}">Q${q}</span>` : `<span class="muted">-</span>`);
  const fmtDate = (d, opts) => new Date(d + "T12:00:00").toLocaleDateString(undefined, opts || { month: "short", day: "numeric" });
  const loc = (l) => ({ home: "vs", away: "at", neutral: "N" }[l] || l);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };

  function chrome(active) {
    const h = document.createElement("header");
    h.className = "site";
    h.innerHTML = `<div class="wrap"><a class="brand" href="index.html">CBB <span>Ratings</span></a><nav class="main">${PAGES.map(
      ([href, label, key]) => `<a href="${href}" class="${key === active ? "on" : ""}">${label}</a>`
    ).join("")}</nav></div>`;
    document.body.prepend(h);
    get("meta.json").then((m) => {
      const f = document.createElement("footer");
      f.className = "site";
      f.innerHTML = `${esc(m.season_label)} season · ratings through games before ${esc(fmtDate(m.as_of, { month: "long", day: "numeric", year: "numeric" }))} · ${m.games_rated} D-I games · data: ESPN via sportsdataverse/hoopR`;
      document.body.append(f);
      document.querySelectorAll("[data-asof]").forEach((el) => (el.textContent = fmtDate(m.as_of, { month: "long", day: "numeric" })));
    }).catch(() => {});
  }

  // Sortable table. cols: {key, label, html(row), val(row), cls, asc, title}
  function table(el, cols, rows, opts = {}) {
    let sortKey = opts.sort || null, asc = !!opts.asc;
    const groups = opts.groups;
    function draw() {
      let data = rows.slice();
      if (sortKey) {
        const c = cols.find((c) => c.key === sortKey);
        const v = c.val || ((r) => r[c.key]);
        data.sort((a, b) => {
          const x = v(a), y = v(b);
          if (x == null) return 1;
          if (y == null) return -1;
          return (x < y ? -1 : x > y ? 1 : 0) * (asc ? 1 : -1);
        });
      }
      const gh = groups ? `<tr>${groups.map(([label, span]) => `<th class="nosort grp" colspan="${span}">${label}</th>`).join("")}</tr>` : "";
      el.innerHTML = `<table class="data"><thead>${gh}<tr>${cols.map((c) =>
        `<th data-k="${c.key}" class="${c.cls || ""} ${c.nosort ? "nosort" : ""} ${c.key === sortKey ? "sorted" + (asc ? " asc" : "") : ""}" ${c.title ? `title="${esc(c.title)}"` : ""}>${c.label}</th>`
      ).join("")}</tr></thead><tbody>${data.map((r, i) =>
        `<tr class="${opts.rowClass ? opts.rowClass(r) : ""}">${cols.map((c) =>
          `<td class="${c.cls || ""}">${c.html ? c.html(r, i) : esc(r[c.key])}</td>`).join("")}</tr>`
      ).join("")}</tbody></table>`;
      el.querySelectorAll("th[data-k]").forEach((th) => th.addEventListener("click", () => {
        const c = cols.find((c) => c.key === th.dataset.k);
        if (c.nosort) return;
        if (sortKey === c.key) asc = !asc; else { sortKey = c.key; asc = !!c.asc; }
        draw();
      }));
    }
    draw();
    return { set(newRows) { rows = newRows; draw(); } };
  }

  function filters(rows, onChange, key) {
    const box = document.getElementById("controls");
    const confs = [...new Set(rows.map((r) => r.conf).filter(Boolean))].sort();
    box.insertAdjacentHTML("afterbegin",
      `<input type="search" id="q" placeholder="Search teams" aria-label="Search teams">
       <select id="conf" aria-label="Conference"><option value="">All conferences</option>${confs.map((c) => `<option>${esc(c)}</option>`).join("")}</select>`);
    const q = box.querySelector("#q"), conf = box.querySelector("#conf");
    conf.value = store.get(key + ":conf") || "";
    const apply = () => {
      store.set(key + ":conf", conf.value);
      const s = q.value.trim().toLowerCase();
      onChange(rows.filter((r) => (!conf.value || r.conf === conf.value) && (!s || r.name.toLowerCase().includes(s))));
    };
    q.addEventListener("input", apply);
    conf.addEventListener("change", apply);
    apply();
  }

  function seg(id, options, current, onPick) {
    const el = document.getElementById(id);
    el.className = "seg";
    el.innerHTML = options.map(([v, l]) => `<button data-v="${v}" class="${v === current ? "on" : ""}">${l}</button>`).join("");
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      el.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      onPick(b.dataset.v);
    });
  }

  // ---------- Ratings page
  async function ratings() {
    const rows = await get("ratings.json");
    const team = { key: "name", label: "Team", cls: "l", html: (r) => `<div class="team">${teamLink(r.team_id, r.name, r.logo)}</div>`, asc: true };
    const base = [
      { key: "rank", label: "Rk", asc: true },
      { ...team, html: (r) => `<div class="team">${teamLink(r.team_id, r.short, r.logo)}</div>` },
      { key: "conf", label: "Conf", cls: "l hide-sm", asc: true },
      { key: "wins", label: "W-L", html: (r) => `${r.wins}-${r.losses}`, val: (r) => r.wins - r.losses },
    ];
    const views = {
      eff: [
        ...base,
        { key: "adj_em", label: "AdjEM", html: (r) => `<span class="em">${sgn(r.adj_em, 2)}</span>`, title: "Adjusted efficiency margin: points per 100 possessions better than an average D-I team" },
        { key: "adj_o", label: "AdjO", html: (r) => f1(r.adj_o) + rk(r.adj_o_rank) },
        { key: "adj_d", label: "AdjD", html: (r) => f1(r.adj_d) + rk(r.adj_d_rank), asc: true },
        { key: "adj_t", label: "AdjT", html: (r) => f1(r.adj_t) + rk(r.adj_t_rank) },
        { key: "luck", label: "Luck", html: (r) => sgn(r.luck, 3) + rk(r.luck_rank), cls: "hide-sm" },
        { key: "sos_em", label: "SOS", html: (r) => sgn(r.sos_em, 2) + rk(r.sos_em_rank), cls: "hide-sm", title: "Average AdjEM of D-I opponents" },
        { key: "ncsos_em", label: "NCSOS", html: (r) => sgn(r.ncsos_em, 2), cls: "hide-sm", title: "Non-conference SOS" },
        { key: "netplus_rank", label: "NET+", asc: true },
      ],
      ff: [
        ...base,
        { key: "adj_em", label: "AdjEM", html: (r) => sgn(r.adj_em, 2) },
        { key: "o_efg", label: "eFG%", html: (r) => f1(r.o_efg) },
        { key: "o_to", label: "TO%", html: (r) => f1(r.o_to), asc: true },
        { key: "o_or", label: "OR%", html: (r) => f1(r.o_or) },
        { key: "o_ftr", label: "FTR", html: (r) => f1(r.o_ftr) },
        { key: "d_efg", label: "eFG%", html: (r) => f1(r.d_efg), asc: true },
        { key: "d_to", label: "TO%", html: (r) => f1(r.d_to) },
        { key: "d_or", label: "OR%", html: (r) => f1(r.d_or), asc: true },
        { key: "d_ftr", label: "FTR", html: (r) => f1(r.d_ftr), asc: true },
      ],
      raw: [
        ...base,
        { key: "raw_o", label: "OE", html: (r) => f1(r.raw_o), title: "Raw points per 100 possessions" },
        { key: "raw_d", label: "DE", html: (r) => f1(r.raw_d), asc: true },
        { key: "raw_em", label: "Raw EM", val: (r) => r.raw_o - r.raw_d, html: (r) => sgn(r.raw_o - r.raw_d, 2) },
        { key: "raw_t", label: "Tempo", html: (r) => f1(r.raw_t) },
        { key: "adj_em", label: "AdjEM", html: (r) => sgn(r.adj_em, 2) },
      ],
    };
    const groups = { ff: [["", 4], ["", 1], ["Offense", 4], ["Defense", 4]] };
    const el = document.getElementById("table");
    let view = store.get("ratings:view") || "eff";
    let current = rows;
    let t;
    const draw = () => (t = table(el, views[view], current, { sort: "rank", asc: true, groups: groups[view] }));
    seg("view", [["eff", "Efficiency"], ["ff", "Four Factors"], ["raw", "Raw"]], view, (v) => { view = v; store.set("ratings:view", v); draw(); });
    filters(rows, (r) => { current = r; t ? t.set(r) : draw(); }, "ratings");
  }

  // ---------- NET+ page
  async function netplus() {
    const rows = await get("netplus.json");
    let kind = "frozen";
    const qcol = (q) => ({
      key: `q${q}`, label: `Q${q}`, val: (r) => r[`q${q}_${kind}_w`] - r[`q${q}_${kind}_l`] * 0.5,
      html: (r) => `${r[`q${q}_${kind}_w`]}-${r[`q${q}_${kind}_l`]}`,
    });
    const cols = () => [
      { key: "netplus_rank", label: "NET+", asc: true },
      { key: "name", label: "Team", cls: "l", asc: true, html: (r) => `<div class="team">${teamLink(r.team_id, r.short, r.logo)}</div>` },
      { key: "conf", label: "Conf", cls: "l hide-sm", asc: true },
      { key: "wins", label: "W-L", html: (r) => `${r.wins}-${r.losses}`, val: (r) => r.wins - r.losses },
      { key: kind === "frozen" ? "wab_frozen" : "wab_live", label: "WAB", html: (r) => sgn(kind === "frozen" ? r.wab_frozen : r.wab_live, 2), title: "Wins above a bubble team against the same schedule" },
      qcol(1), qcol(2), qcol(3), qcol(4),
      { key: "netstyle_rank", label: "Live rank", asc: true, title: "Same formula, but every game regraded with today's rankings (how NET works)" },
      { key: "delta", label: "Freeze effect", val: (r) => r.netstyle_rank - r.netplus_rank,
        html: (r) => { const d = r.netstyle_rank - r.netplus_rank; return d ? `<span class="${d > 0 ? "pos" : "neg"}">${d > 0 ? "+" : ""}${d}</span>` : `<span class="muted">0</span>`; },
        title: "Spots gained (+) or lost by freezing each game at the time it was played" },
      { key: "rank", label: "AdjEM rk", asc: true, cls: "hide-sm" },
    ];
    const el = document.getElementById("table");
    let current = rows, t;
    const draw = () => (t = table(el, cols(), current, { sort: "netplus_rank", asc: true }));
    seg("view", [["frozen", "Quadrants at game time"], ["live", "Quadrants today"]], kind, (v) => { kind = v; draw(); });
    filters(rows, (r) => { current = r; t ? t.set(r) : draw(); }, "netplus");
  }

  // ---------- Team page
  async function teamPage() {
    const id = new URLSearchParams(location.search).get("id");
    const box = document.getElementById("team");
    if (!id) { box.textContent = "No team selected."; return; }
    const d = await get(`teams/${encodeURIComponent(id)}.json`);
    const t = d.team, n = d.netplus;
    document.title = `${t.name} · CBB Ratings`;
    const card = (k, v, r) => `<div class="card stat"><div class="k">${k}</div><div class="v">${v}</div><div class="r">${r || "&nbsp;"}</div></div>`;
    const ord = (x) => (x == null ? "" : `#${Math.round(x)}`);
    box.innerHTML = `
      <div class="team-head">${t.logo ? `<img src="${esc(t.logo)}" alt="" onerror="this.remove()">` : ""}<div><h1>${esc(t.name)}</h1>
      <p class="sub">${esc(t.conf)} · ${t.wins}-${t.losses} (${t.conf_wins}-${t.conf_losses} conf)</p></div></div>
      <div class="stats">
        ${card("AdjEM", sgn(t.adj_em, 2), ord(t.rank))}
        ${card("AdjO", f1(t.adj_o), ord(t.adj_o_rank))}
        ${card("AdjD", f1(t.adj_d), ord(t.adj_d_rank))}
        ${card("AdjT", f1(t.adj_t), ord(t.adj_t_rank))}
        ${card("NET+", "#" + n.netplus_rank, `live-graded #${n.netstyle_rank}`)}
        ${card("WAB (frozen)", sgn(n.wab_frozen, 2), `live ${sgn(n.wab_live, 2)}`)}
        ${card("Luck", sgn(t.luck, 3), ord(t.luck_rank))}
        ${card("SOS", sgn(t.sos_em, 2), ord(t.sos_em_rank))}
      </div>
      <div id="hist"></div>
      <h2>Results</h2>
      <p class="note">Opponent rank and quadrant are shown <b>at game time</b> (frozen, used by NET+) and <b>today</b>. Highlighted rows changed quadrant since the game.</p>
      <div class="table-wrap" id="log"></div>
      <div id="up"></div>
      <h2>Four Factors</h2>
      <div class="table-wrap" id="ff"></div>`;

    if (d.rank_history && d.rank_history.dates.length > 1) {
      const { dates, ranks } = d.rank_history;
      const W = 760, H = 140, pad = 28, maxR = Math.max(60, ...ranks);
      const x = (i) => pad + (i / (dates.length - 1)) * (W - pad * 2);
      const y = (r) => 14 + ((r - 1) / (maxR - 1)) * (H - 36);
      const pts = ranks.map((r, i) => `${x(i).toFixed(1)},${y(r).toFixed(1)}`).join(" ");
      document.getElementById("hist").innerHTML = `<h2>AdjEM rank by day</h2><div class="card" style="padding:8px 12px">
        <svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="AdjEM rank by day">
          <line x1="${pad}" x2="${W - pad}" y1="${y(1)}" y2="${y(1)}" stroke="var(--line)"/>
          <line x1="${pad}" x2="${W - pad}" y1="${y(maxR)}" y2="${y(maxR)}" stroke="var(--line)"/>
          <text x="2" y="${y(1) + 4}" font-size="11" fill="var(--muted)">#1</text>
          <text x="2" y="${y(maxR) + 4}" font-size="11" fill="var(--muted)">#${maxR}</text>
          <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
          <text x="${pad}" y="${H - 4}" font-size="11" fill="var(--muted)">${esc(fmtDate(dates[0]))}</text>
          <text x="${W - pad}" y="${H - 4}" font-size="11" fill="var(--muted)" text-anchor="end">${esc(fmtDate(dates[dates.length - 1]))} · #${ranks[ranks.length - 1]}</text>
        </svg></div>`;
    }

    table(document.getElementById("log"), [
      { key: "game_date", label: "Date", cls: "l", html: (g) => fmtDate(g.game_date) },
      { key: "opp", label: "Opponent", cls: "l", html: (g) => `${loc(g.location)} ${g.d1 ? `<a href="team.html?id=${g.opp_id}">${esc(g.opp)}</a>` : `<span class="muted">${esc(g.opp)}</span>`}` },
      { key: "win", label: "Result", cls: "l", html: (g) => `<span class="${g.win ? "pos" : "neg"}">${g.win ? "W" : "L"}</span> ${g.pts}-${g.opp_pts}` },
      { key: "opp_rank_frozen", label: "Opp rk then", asc: true, html: (g) => g.opp_rank_frozen ?? "" },
      { key: "opp_rank_live", label: "Opp rk now", asc: true, html: (g) => g.opp_rank_live ?? "" },
      { key: "quad_frozen", label: "Quad then", asc: true, html: (g) => (g.d1 ? qBadge(g.quad_frozen) : `<span class="muted">non-D-I</span>`) },
      { key: "quad_live", label: "Quad now", asc: true, html: (g) => (g.d1 ? qBadge(g.quad_live) : "") },
      { key: "wab_frozen", label: "WAB", html: (g) => (g.d1 ? sgn(g.wab_frozen, 2) : "") },
      { key: "poss", label: "Poss", html: (g) => f1(g.poss), cls: "hide-sm" },
    ], d.games, { sort: "game_date", asc: true, rowClass: (g) => (g.d1 && g.quad_frozen !== g.quad_live ? "flag" : "") });

    if (d.upcoming.length) {
      const up = document.getElementById("up");
      up.innerHTML = `<h2>Upcoming</h2><div class="table-wrap" id="upt"></div>`;
      table(document.getElementById("upt"), [
        { key: "game_date", label: "Date", cls: "l", html: (g) => fmtDate(g.game_date) },
        { key: "opp", label: "Opponent", cls: "l", html: (g) => `${loc(g.location)} <a href="team.html?id=${g.opp_id}">${esc(g.opp)}</a> <span class="rk">${g.opp_rank}</span>` },
        { key: "proj", label: "Projected", nosort: true, html: (g) => `${Math.round(g.pts)}-${Math.round(g.opp_pts)}` },
        { key: "win_prob", label: "Win %", html: (g) => `${Math.min(99, Math.max(1, Math.round(g.win_prob * 100)))}%` },
      ], d.upcoming.slice(0, 40), { sort: "game_date", asc: true });
    }

    const ffRows = [
      { s: "Offense", efg: t.o_efg, to: t.o_to, or: t.o_or, ftr: t.o_ftr },
      { s: "Defense", efg: t.d_efg, to: t.d_to, or: t.d_or, ftr: t.d_ftr },
    ];
    table(document.getElementById("ff"), [
      { key: "s", label: "", cls: "l", nosort: true },
      { key: "efg", label: "eFG%", nosort: true, html: (r) => f1(r.efg) },
      { key: "to", label: "TO%", nosort: true, html: (r) => f1(r.to) },
      { key: "or", label: "OR%", nosort: true, html: (r) => f1(r.or) },
      { key: "ftr", label: "FTA/FGA", nosort: true, html: (r) => f1(r.ftr) },
    ], ffRows);
  }

  // ---------- Games page
  async function games() {
    const rows = await get("games.json");
    const el = document.getElementById("games");
    if (!rows.length) { el.innerHTML = `<p class="loading">No D-I games scheduled in the next week.</p>`; return; }
    let topOnly = store.get("games:top") === "1";
    const draw = () => {
      const list = topOnly ? rows.filter((g) => Math.min(g.h_rank, g.a_rank) <= 50) : rows;
      const byDay = {};
      list.forEach((g) => (byDay[g.game_date] = byDay[g.game_date] || []).push(g));
      el.innerHTML = Object.keys(byDay).sort().map((day) => `<div class="day">${esc(fmtDate(day, { weekday: "long", month: "long", day: "numeric" }))} · ${byDay[day].length} games</div>
        <div class="games">${byDay[day].map((g) => {
          const pa = 1 - g.p_home, ph = g.p_home;
          const pct = (x) => Math.min(99, Math.max(1, Math.round(x * 100))) + "%";
          const time = new Date(g.tip).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
          const fav = g.margin >= 0 ? g.home : g.away;
          return `<div class="card game">
            <div class="row"><span class="nm"><span class="rk">${g.a_rank}</span> <a href="team.html?id=${g.a_team_id}">${esc(g.away)}</a></span><span class="pts">${Math.round(g.pts_a)} · ${pct(pa)}</span></div>
            <div class="row"><span class="nm"><span class="rk">${g.h_rank}</span> ${g.neutral_site ? "<span class=muted>vs</span>" : "<span class=muted>at</span>"} <a href="team.html?id=${g.h_team_id}">${esc(g.home)}</a></span><span class="pts">${Math.round(g.pts_h)} · ${pct(ph)}</span></div>
            <div class="bar"><i style="width:${(pa * 100).toFixed(1)}%"></i></div>
            <div class="meta"><span>${esc(time)}${g.neutral_site ? " · neutral" : ""}</span><span>${esc(fav)} by ${Math.abs(g.margin).toFixed(1)} · ${Math.round(g.tempo)} poss</span></div>
          </div>`;
        }).join("")}</div>`).join("");
    };
    seg("view", [["0", "All games"], ["1", "Top-50 teams"]], topOnly ? "1" : "0", (v) => { topOnly = v === "1"; store.set("games:top", v); draw(); });
    draw();
  }

  window.CBB = {
    start(page) {
      chrome(page === "team" ? "" : page);
      const run = { ratings, netplus, team: teamPage, games, about: async () => {} }[page];
      run().catch((e) => {
        const m = document.querySelector("main");
        m.insertAdjacentHTML("beforeend", `<p class="loading">Couldn't load data (${esc(e.message)}).</p>`);
      });
    },
  };
})();
