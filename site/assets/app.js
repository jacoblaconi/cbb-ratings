"use strict";
(function () {
  const PAGES = [
    ["index.html", "Ratings", "ratings"],
    ["netplus.html", "NET+", "netplus"],
    ["games.html", "Games", "games"],
    ["bracket.html", "Bracket", "bracket"],
    ["players.html", "Players", "players"],
    ["tracker.html", "Tracker", "tracker"],
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
      onChange(rows.filter((r) => (!conf.value || r.conf === conf.value) && (!s || (r._s || r.name.toLowerCase()).includes(s))));
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
      ${t.pre_em != null ? `<p class="note">Preseason projection: AdjEM ${sgn(t.pre_em, 1)} (#${Math.round(t.pre_rank)}), with ${Math.round(t.pre_ret * 100)}% of last season's production returning. Incoming transfers produced the equivalent of ${Math.round(t.pre_xfer * 100)}% of a team's output at their old schools. The projection now counts as ${f1(t.prior_weight)} games of data and fades to zero by game ${t.prior_fade}.</p>` : ""}
      <div id="outlook"></div>
      <div id="hist"></div>
      <h2>Results</h2>
      <p class="note">Opponent rank and quadrant are shown <b>at game time</b> (frozen, used by NET+) and <b>today</b>. Highlighted rows changed quadrant since the game.</p>
      <div class="table-wrap" id="log"></div>
      <div id="up"></div>
      <div id="roster"></div>
      <h2>Four Factors</h2>
      <div class="table-wrap" id="ff"></div>`;

    const ol = d.outlook;
    if (ol) {
      document.getElementById("outlook").innerHTML = `<h2>Season outlook</h2><div class="stats">
        ${card("Projected record", `${Math.round(ol.proj_w)}-${Math.round(ol.proj_l)}`, `${Math.round(ol.proj_cw)}-${Math.round(ol.proj_cl)} in conference`)}
        ${card("Conference title", pctf(ol.p_reg_title), "regular season, incl. ties")}
        ${card("Auto bid", pctf(ol.p_auto), "wins conference tournament")}
        ${card("Makes NCAA field", pctf(ol.p_field), ol.p_field >= 0.01 ? `average seed ${f1(ol.avg_seed)}` : "")}
        ${card("Sweet 16", pctf(ol.p_s16), `Final Four ${pctf(ol.p_f4, 1)}`)}
        ${card("Title", pctf(ol.p_champ, 1), "")}
      </div><p class="note">From simulating the rest of the season, the conference tournament and the NCAA tournament. <a href="bracket.html">Bracketology</a></p>`;
    }

    if (d.players && d.players.length) {
      document.getElementById("roster").innerHTML = `<h2>Players</h2><div class="table-wrap" id="pl"></div>
        <p class="note">ORtg is points produced per 100 possessions used; Usg% is the share of team possessions a player uses while on the floor. Rates are left blank for players under 10% of minutes. <a href="players.html">All players</a></p>`;
      table(document.getElementById("pl"), [
        { key: "name", label: "Player", cls: "l", asc: true, html: (p) => `${p.jersey ? `<span class="muted">${esc(p.jersey)}</span> ` : ""}${esc(p.name)} <span class="muted">${esc(p.pos || "")}</span>` },
        { key: "g", label: "G" },
        { key: "mpg", label: "MPG", html: (p) => f1(p.mpg) },
        { key: "min_pct", label: "Min%", html: (p) => f1(p.min_pct) },
        { key: "ppg", label: "PPG", html: (p) => f1(p.ppg) },
        { key: "ortg", label: "ORtg", html: (p) => f1(p.ortg) },
        { key: "usg", label: "Usg%", html: (p) => f1(p.usg) },
        { key: "off_value", label: "Off. value", html: (p) => sgn(p.off_value, 1), title: "Points per 100 team possessions added over an average D-I offense" },
        { key: "efg", label: "eFG%", html: (p) => f1(p.efg), cls: "hide-sm" },
        { key: "ts", label: "TS%", html: (p) => f1(p.ts), cls: "hide-sm" },
        { key: "ast_rate", label: "ARate", html: (p) => f1(p.ast_rate), cls: "hide-sm" },
        { key: "to_rate", label: "TORate", html: (p) => f1(p.to_rate), asc: true, cls: "hide-sm" },
        { key: "or_pct", label: "OR%", html: (p) => f1(p.or_pct), cls: "hide-sm" },
        { key: "dr_pct", label: "DR%", html: (p) => f1(p.dr_pct), cls: "hide-sm" },
      ], d.players, { sort: "min_pct", asc: false });
    }

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
  function gameCard(g) {
    const pa = 1 - g.p_home, ph = g.p_home;
    const pct = (x) => Math.min(99, Math.max(1, Math.round(x * 100))) + "%";
    const time = new Date(g.tip).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    const fav = g.margin >= 0 ? g.home : g.away;
    return `<div class="card game">
      <div class="row"><span class="nm"><span class="rk">${g.a_rank}</span> <a href="team.html?id=${g.a_team_id}">${esc(g.away)}</a></span><span class="pts">${Math.round(g.pts_a)} · ${pct(pa)}</span></div>
      <div class="row"><span class="nm"><span class="rk">${g.h_rank}</span> ${g.neutral_site ? "<span class=muted>vs</span>" : "<span class=muted>at</span>"} <a href="team.html?id=${g.h_team_id}">${esc(g.home)}</a></span><span class="pts">${Math.round(g.pts_h)} · ${pct(ph)}</span></div>
      <div class="bar"><i style="width:${(pa * 100).toFixed(1)}%"></i></div>
      <div class="meta"><span>${esc(time)}${g.neutral_site ? " · neutral" : ""}</span><span>${esc(fav)} by ${Math.abs(g.margin).toFixed(1)} · ${Math.round(g.tempo)} poss</span></div>
      <div class="meta"><span title="Watch score: both teams good and the game close (0-100)">Watch <b class="watch">${Math.round(g.watch)}</b></span></div>
    </div>`;
  }

  async function games() {
    const rows = await get("games.json");
    const el = document.getElementById("games");
    const best = document.getElementById("best");
    if (!rows.length) { el.innerHTML = `<p class="loading">No D-I games scheduled in the next week.</p>`; return; }
    // Best games of the next day with games on the schedule.
    const first = rows.map((g) => g.game_date).sort()[0];
    const top = rows.filter((g) => g.game_date === first).sort((a, b) => b.watch - a.watch).slice(0, 6);
    best.innerHTML = `<h2>Best games ${esc(fmtDate(first, { weekday: "long", month: "long", day: "numeric" }))}</h2><div class="games">${top.map(gameCard).join("")}</div>`;
    let mode = store.get("games:mode") || "time";
    const draw = () => {
      let list = mode === "top" ? rows.filter((g) => Math.min(g.h_rank, g.a_rank) <= 50) : rows.slice();
      const byDay = {};
      list.forEach((g) => (byDay[g.game_date] = byDay[g.game_date] || []).push(g));
      el.innerHTML = Object.keys(byDay).sort().map((day) => {
        const gs = byDay[day];
        if (mode === "watch") gs.sort((a, b) => b.watch - a.watch);
        return `<div class="day">${esc(fmtDate(day, { weekday: "long", month: "long", day: "numeric" }))} · ${gs.length} games</div>
        <div class="games">${gs.map(gameCard).join("")}</div>`;
      }).join("");
    };
    seg("view", [["time", "By tip time"], ["watch", "Best first"], ["top", "Top-50 teams"]], mode, (v) => { mode = v; store.set("games:mode", v); draw(); });
    draw();
  }

  const pctf = (x, d = 0) => (x == null ? "" : (x * 100).toFixed(d) + "%");
  // Odds as a percent, with "<1%" and ">99%" at the ends and blank for zero.
  const odds = (x) => (x == null || x === 0 ? `<span class="muted">-</span>` : x < 0.005 ? "<1%" : x > 0.995 && x < 1 ? ">99%" : Math.round(x * 100) + "%");
  const heat = (x) => `<span class="heat" style="--h:${Math.min(1, x || 0).toFixed(3)}">${odds(x)}</span>`;
  const rec = (r) => `${r.w}-${r.l}${r.p ? "-" + r.p : ""}`;
  const recPct = (r) => (r.w + r.l ? ((100 * r.w) / (r.w + r.l)).toFixed(1) + "%" : "");

  // ---------- Bracketology page
  async function bracket() {
    const [b, m] = await Promise.all([get("bracket.json"), get("meta.json")]);
    document.querySelectorAll("[data-sims]").forEach((el) => (el.textContent = Number(b.sims).toLocaleString()));
    const byId = Object.fromEntries(b.teams.map((t) => [t.team_id, t]));
    const nm = (id) => (byId[id] ? byId[id].short : id);
    const p = b.projection;
    const regions = [0, 1, 2, 3].map((r) => p.seeds.filter((s) => s.region === r));
    const tl = (s) => {
      const t = byId[s.team_id];
      return `<li><span class="sd">${s.seed}</span><span class="team">${teamLink(s.team_id, t.short, t.logo)}</span>${s.auto ? `<span class="tag" title="Projected automatic bid">${esc(t.conf)}</span>` : ""}${s.first_four ? `<span class="tag ff" title="First Four">FF</span>` : ""}</li>`;
    };
    const lst = (title, ids) => `<div><div class="k">${title}</div><div>${ids.map((id) => `<a href="team.html?id=${id}">${esc(nm(id))}</a>`).join(", ") || "-"}</div></div>`;
    document.getElementById("proj").innerHTML = `
      <div class="regions">${regions.map((reg, i) => `<div class="card region"><div class="rh">Region ${i + 1}${i === 0 ? ` <span class="muted">· top overall seed</span>` : ""}</div><ol>${reg.map(tl).join("")}</ol></div>`).join("")}</div>
      <div class="card bubble">${lst("Last four byes", p.last_four_byes)}${lst("Last four in", p.last_four_in)}${lst("First four out", p.first_four_out)}${lst("Next four out", p.next_four_out)}</div>
      <p class="note">Region 1 meets Region 4 and Region 2 meets Region 3 in the national semifinals. The bracket follows the S-curve and does not apply the committee's rules for keeping conference teams apart. Auto bids go to each league's likeliest conference tournament champion.</p>`;

    const cols = [
      { key: "sel_score", label: "#", asc: false, html: (r) => r.sel_rank, title: "Order by average selection score across simulations" },
      { key: "short", label: "Team", cls: "l", asc: true, html: (r) => `<div class="team">${teamLink(r.team_id, r.short, r.logo)}</div>` },
      { key: "conf", label: "Conf", cls: "l hide-sm", asc: true },
      { key: "rank", label: "Rk", asc: true, title: "Current AdjEM rank" },
      { key: "proj_w", label: "Proj W-L", html: (r) => `${Math.round(r.proj_w)}-${Math.round(r.proj_l)}`, title: "Average final record, including conference tournament" },
      { key: "proj_cw", label: "Conf", html: (r) => `${Math.round(r.proj_cw)}-${Math.round(r.proj_cl)}`, title: "Average final conference record" },
      { key: "p_reg_title", label: "Reg title", html: (r) => heat(r.p_reg_title), title: "Chance to win or share the regular-season conference title" },
      { key: "p_auto", label: "Auto bid", html: (r) => heat(r.p_auto), title: "Chance to win the conference tournament" },
      { key: "p_field", label: "Make field", html: (r) => heat(r.p_field) },
      { key: "avg_seed", label: "Avg seed", asc: true, html: (r) => (r.p_field >= 0.01 ? f1(r.avg_seed) : ""), val: (r) => (r.p_field >= 0.01 ? r.avg_seed : null), title: "Average seed when in the field" },
      { key: "p_r32", label: "R32", html: (r) => heat(r.p_r32), cls: "hide-sm" },
      { key: "p_s16", label: "S16", html: (r) => heat(r.p_s16) },
      { key: "p_e8", label: "E8", html: (r) => heat(r.p_e8), cls: "hide-sm" },
      { key: "p_f4", label: "F4", html: (r) => heat(r.p_f4) },
      { key: "p_final", label: "Final", html: (r) => heat(r.p_final), cls: "hide-sm" },
      { key: "p_champ", label: "Champ", html: (r) => heat(r.p_champ) },
    ];
    const rows = b.teams.map((t, i) => ({ ...t, name: t.short, sel_rank: i + 1 }));
    const el = document.getElementById("table");
    let current = rows, t;
    const draw = () => (t = table(el, cols, current, { sort: "sel_score", asc: false }));
    document.getElementById("view").remove();
    filters(rows, (r) => { current = r; t ? t.set(r) : draw(); }, "bracket");
  }

  // ---------- Players page
  async function players() {
    const rows = await get("players.json");
    let minPct = Number(store.get("players:min") || 40);
    const cols = [
      { key: "name", label: "Player", cls: "l", asc: true, html: (r) => `${esc(r.name)} <span class="muted">${esc(r.pos || "")}</span>` },
      { key: "team", label: "Team", cls: "l", asc: true, html: (r) => `<a href="team.html?id=${r.team_id}">${esc(r.team)}</a>` },
      { key: "conf", label: "Conf", cls: "l hide-sm", asc: true },
      { key: "g", label: "G" },
      { key: "mpg", label: "MPG", html: (r) => f1(r.mpg) },
      { key: "ppg", label: "PPG", html: (r) => f1(r.ppg) },
      { key: "min_pct", label: "Min%", html: (r) => f1(r.min_pct), title: "Share of team minutes played" },
      { key: "ortg", label: "ORtg", html: (r) => f1(r.ortg), title: "Points produced per 100 possessions used (Dean Oliver)" },
      { key: "usg", label: "Usg%", html: (r) => f1(r.usg), title: "Share of team possessions used while on the floor" },
      { key: "off_value", label: "Off. value", html: (r) => sgn(r.off_value, 1), title: "Points per 100 team possessions added over an average D-I offense: (ORtg − average) × usage × minutes" },
      { key: "efg", label: "eFG%", html: (r) => f1(r.efg), cls: "hide-sm" },
      { key: "ts", label: "TS%", html: (r) => f1(r.ts), cls: "hide-sm" },
      { key: "ast_rate", label: "ARate", html: (r) => f1(r.ast_rate), cls: "hide-sm", title: "Assists per teammate field goal made while on the floor" },
      { key: "to_rate", label: "TORate", html: (r) => f1(r.to_rate), asc: true, cls: "hide-sm", title: "Turnovers per 100 possessions used" },
      { key: "or_pct", label: "OR%", html: (r) => f1(r.or_pct), cls: "hide-sm" },
      { key: "dr_pct", label: "DR%", html: (r) => f1(r.dr_pct), cls: "hide-sm" },
      { key: "rpg", label: "RPG", html: (r) => f1(r.rpg), cls: "hide-sm" },
      { key: "apg", label: "APG", html: (r) => f1(r.apg), cls: "hide-sm" },
    ];
    const el = document.getElementById("table");
    let base = rows, t;
    const visible = () => base.filter((r) => r.min_pct >= minPct).slice();
    const draw = () => (t = table(el, cols, visible(), { sort: "off_value", asc: false }));
    seg("view", [["25", "Min% 25+"], ["40", "40+"], ["60", "60+"]], String(minPct), (v) => { minPct = Number(v); store.set("players:min", v); t.set(visible()); });
    // Search players by name or team.
    filters(rows.map((r) => ({ ...r, name: r.name, _s: (r.name + " " + r.team).toLowerCase() })), (r) => { base = r; t ? t.set(visible()) : draw(); }, "players");
    document.getElementById("q").placeholder = "Search players";
  }

  // ---------- Tracker page
  async function tracker() {
    const d = await get("tracker.json");
    const box = document.getElementById("summary");
    const o = d.overall, w7 = d.last7;
    if (!o.games) { box.innerHTML = `<p class="loading">No games graded yet.</p>`; return; }
    const card = (k, v, r) => `<div class="card stat"><div class="k">${k}</div><div class="v">${v}</div><div class="r">${r || "&nbsp;"}</div></div>`;
    const su = (s) => `${s.su_w}-${s.su_l}`;
    const suPct = (s) => ((100 * s.su_w) / s.games).toFixed(1) + "%";
    box.innerHTML = `
      <div class="stats">
        ${card("Winners picked", suPct(o), `${su(o)} · last 7 days ${w7.games ? suPct(w7) : "-"}`)}
        ${card("Avg error (margin)", f1(o.mae), `pts · last 7 days ${w7.games ? f1(w7.mae) : "-"}`)}
        ${card("Brier score", o.brier.toFixed(3), "win chance accuracy, lower is better")}
        ${card("Against the spread", recPct(o.ats), `${rec(o.ats)} · ${o.lined} games with lines`)}
        ${card("ATS, 3+ pt edge", recPct(o.ats_big), rec(o.ats_big))}
        ${card("Over/under", recPct(o.ou), rec(o.ou))}
        ${o.vegas_mae != null ? card("Vegas avg error", f1(o.vegas_mae), `model ${f1(o.model_mae_lined)} on the same games`) : ""}
        ${o.vegas_su_n ? card("Vegas winners", ((100 * o.vegas_su_w) / o.vegas_su_n).toFixed(1) + "%", `model ${((100 * o.model_su_w_lined) / o.vegas_su_n).toFixed(1)}% on the same games`) : ""}
      </div>
      <p class="note">A pick against the spread takes the side the model favors relative to the line. 52.4% is break-even at standard −110 odds.</p>
      <h2>Calibration</h2><div class="card" style="padding:8px 12px" id="cal"></div>
      <p class="note">Each dot is a group of games by the favorite's predicted chance (left to right) against how often favorites actually won. Dots on the line mean the percentages can be taken at face value. Dot size reflects the number of games.</p>
      <h2>By week</h2><div class="table-wrap" id="weeks"></div>
      <h2>Recent games</h2><div class="controls"><div id="view"></div></div><div class="table-wrap" id="recent"></div>`;

    // Calibration plot.
    const W = 420, H = 300, pl = 44, pb = 36, pt = 12, pr = 22;
    const x = (v) => pl + ((v - 0.5) / 0.5) * (W - pl - pr);
    const y = (v) => pt + (1 - (v - 0.5) / 0.5) * (H - pt - pb);
    const maxN = Math.max(...d.calibration.map((c) => c.n));
    const ticks = [0.5, 0.6, 0.7, 0.8, 0.9, 1];
    document.getElementById("cal").innerHTML = `<svg class="spark" viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="Calibration chart">
      ${ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="${y(0.5)}" y2="${y(1)}" stroke="var(--line)"/><line x1="${x(0.5)}" x2="${x(1)}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)"/>
        <text x="${x(t)}" y="${H - pb + 16}" font-size="11" text-anchor="middle" fill="var(--muted)">${t * 100}%</text>
        <text x="${pl - 6}" y="${y(t) + 4}" font-size="11" text-anchor="end" fill="var(--muted)">${t * 100}%</text>`).join("")}
      <line x1="${x(0.5)}" y1="${y(0.5)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--muted)" stroke-dasharray="4 4"/>
      ${d.calibration.map((c) => `<circle cx="${x(c.pred).toFixed(1)}" cy="${y(Math.max(0.5, c.actual)).toFixed(1)}" r="${(3 + 7 * Math.sqrt(c.n / maxN)).toFixed(1)}" fill="var(--accent)" fill-opacity="0.8"><title>${Math.round(c.lo * 100)}-${Math.round(c.hi * 100)}%: predicted ${pctf(c.pred, 1)}, won ${pctf(c.actual, 1)} of ${c.n}</title></circle>`).join("")}
      <text x="${(pl + W - pr) / 2}" y="${H - 4}" font-size="11" text-anchor="middle" fill="var(--muted)">Favorite's predicted chance</text>
    </svg>`;

    table(document.getElementById("weeks"), [
      { key: "week", label: "Week of", cls: "l", html: (r) => fmtDate(r.week) },
      { key: "games", label: "Games" },
      { key: "su", label: "Winners", val: (r) => r.su_w / r.games, html: (r) => `${r.su_w}-${r.su_l} <span class="muted">${suPct(r)}</span>` },
      { key: "mae", label: "Avg error", html: (r) => f1(r.mae), asc: true },
      { key: "vegas_mae", label: "Vegas error", html: (r) => f1(r.vegas_mae), asc: true },
      { key: "brier", label: "Brier", html: (r) => r.brier.toFixed(3), asc: true, cls: "hide-sm" },
      { key: "ats", label: "ATS", val: (r) => r.ats.w / (r.ats.w + r.ats.l || 1), html: (r) => `${rec(r.ats)} <span class="muted">${recPct(r.ats)}</span>` },
      { key: "ou", label: "O/U", val: (r) => r.ou.w / (r.ou.w + r.ou.l || 1), html: (r) => `${rec(r.ou)} <span class="muted">${recPct(r.ou)}</span>`, cls: "hide-sm" },
    ], d.weeks, { sort: "week", asc: false });

    const res = (k) => (k === "W" ? `<span class="pos">W</span>` : k === "L" ? `<span class="neg">L</span>` : k === "P" ? "P" : `<span class="muted">-</span>`);
    const spreadTxt = (g) => {
      if (g.home_spread == null) return `<span class="muted">-</span>`;
      if (g.home_spread === 0) return "PK";
      return g.home_spread < 0 ? `${esc(g.home)} ${g.home_spread}` : `${esc(g.away)} ${-g.home_spread}`;
    };
    const pickTxt = (g) => {
      const fav = g.margin >= 0 ? g.home : g.away;
      return `${esc(fav)} by ${Math.abs(g.margin).toFixed(1)}`;
    };
    const cols = [
      { key: "game_date", label: "Date", cls: "l", html: (g) => fmtDate(g.game_date) },
      { key: "away", label: "Game", cls: "l", nosort: true, html: (g) => `<a href="team.html?id=${g.a_team_id}">${esc(g.away)}</a> ${g.a_score} ${g.neutral_site ? "vs" : "at"} <a href="team.html?id=${g.h_team_id}">${esc(g.home)}</a> ${g.h_score}` },
      { key: "margin", label: "Model pick", cls: "l", nosort: true, html: (g) => `${pickTxt(g)} <span class="muted">${Math.round(Math.max(g.p_home, 1 - g.p_home) * 100)}%</span>` },
      { key: "correct", label: "Winner", html: (g) => res(g.correct ? "W" : "L") },
      { key: "home_spread", label: "Line", cls: "l", nosort: true, html: spreadTxt },
      { key: "ats_edge", label: "Edge", val: (g) => (g.ats_edge == null ? null : Math.abs(g.ats_edge)), html: (g) => (g.ats_edge == null ? "" : f1(Math.abs(g.ats_edge))), title: "Points between the model's margin and the line" },
      { key: "ats", label: "ATS", html: (g) => res(g.ats) },
      { key: "ou", label: "O/U", html: (g) => res(g.ou), cls: "hide-sm" },
    ];
    const el = document.getElementById("recent");
    let mode = "all";
    const tb = table(el, cols, d.games, { sort: "game_date", asc: false });
    seg("view", [["all", "All"], ["edge", "3+ pt edge"], ["miss", "Missed winners"]], mode, (v) => {
      mode = v;
      tb.set(d.games.filter((g) => v === "all" || (v === "edge" ? g.ats_edge != null && Math.abs(g.ats_edge) >= 3 : !g.correct)));
    });
  }

  window.CBB = {
    start(page) {
      chrome(page === "team" ? "" : page);
      const run = { ratings, netplus, team: teamPage, games, bracket, players, tracker, about: async () => {} }[page];
      run().catch((e) => {
        const m = document.querySelector("main");
        m.insertAdjacentHTML("beforeend", `<p class="loading">Couldn't load data (${esc(e.message)}).</p>`);
      });
    },
  };
})();
