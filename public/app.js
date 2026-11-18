/* ZVD Radar dashboard - vanilla JS, no build step. */

const state = {
  data: null,
  tab: "topics",
  audience: "All",
  theme: "all",
  sort: "score",
  intentSort: "value",
  poll: null,
  competitors: null,
  compState: {},
  compPoll: null,
  publishing: null,
  pubState: {},
  pubPoll: null,
};

const $ = (id) => document.getElementById(id);

const escapeHtml = (value) =>
  String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));

function shortDate(iso) {
  if (!iso) return "undated";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "undated";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function longDate(iso) {
  if (!iso) return "—";
  const date = new Date(iso.length <= 10 ? iso + "T12:00:00" : iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
}

function ago(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const hours = (Date.now() - then) / 36e5;
  if (hours < 1) return "just now";
  if (hours < 24) return Math.round(hours) + "h ago";
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : days + "d ago";
}

function momentumPill(topic) {
  if (topic.momentum === "Rising") return `<span class="pill rising">▲ Rising ${topic.change_pct != null ? Math.abs(topic.change_pct) + "%" : ""}</span>`;
  if (topic.momentum === "Cooling") return `<span class="pill cooling">▼ Cooling ${topic.change_pct != null ? Math.abs(topic.change_pct) + "%" : ""}</span>`;
  if (topic.momentum === "New") return `<span class="pill">New this scan</span>`;
  return `<span class="pill">Steady</span>`;
}

/* ---------- data ---------- */
async function load() {
  try {
    const response = await fetch("/api/radar", { cache: "no-store" });
    state.data = await response.json();
    render();
  } catch (error) {
    showStatus("Could not reach the radar service: " + error.message, true);
  }
}

async function runScan() {
  const button = $("run-scan");
  button.disabled = true;
  showStatus("Starting scan…", false);
  try {
    const response = await fetch("/api/scan", { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.started === false) {
      showStatus(payload.error || "The scan could not be started on this deployment.", true);
      button.disabled = false;
      return;
    }
  } catch (error) {
    showStatus("Could not start the scan: " + error.message, true);
    button.disabled = false;
    return;
  }
  pollUntilDone();
}

function pollUntilDone() {
  clearTimeout(state.poll);
  state.poll = setTimeout(async () => {
    await load();
    const scan = state.data && state.data.state;
    if (scan && scan.running) {
      pollUntilDone();
    } else {
      $("run-scan").disabled = false;
    }
  }, 2200);
}

function showStatus(message, isError) {
  const node = $("status");
  node.classList.remove("hidden");
  node.classList.toggle("error", Boolean(isError));
  node.innerHTML = isError
    ? escapeHtml(message)
    : `<span class="dot"></span><span>${escapeHtml(message)}</span>`;
}

function hideStatus() {
  $("status").classList.add("hidden");
}

/* ---------- render ---------- */
function render() {
  const payload = state.data || {};
  const snapshot = payload.snapshot;
  const scan = payload.state || {};

  if (scan.running) {
    $("run-scan").disabled = true;
    showStatus(scan.step + (scan.seconds ? " · " + scan.seconds + "s" : ""), false);
  } else if (scan.error) {
    $("run-scan").disabled = false;
    showStatus("Scan failed — " + scan.error, true);
  } else {
    $("run-scan").disabled = false;
    hideStatus();
  }

  if (!snapshot) {
    $("snapshot-date").textContent = longDate(new Date().toISOString().slice(0, 10));
    $("snapshot-meta").textContent = scan.running ? "scanning the web…" : "no scan yet";
    $("kpis").innerHTML = "";
    $("topic-grid").innerHTML = `<div class="empty" style="grid-column:1/-1">No snapshot yet. The first scan takes about half a minute.<br><br><button class="btn" onclick="runScan()">Run the first scan</button></div>`;
    return;
  }

  $("snapshot-date").textContent = longDate(snapshot.date);
  const finished = snapshot.scan_seconds ? snapshot.scan_seconds + "s scan" : "";
  const warnings = snapshot.stats.error_count;
  $("snapshot-meta").textContent = [
    "updated " + ago(snapshot.generated_at),
    finished,
    warnings ? warnings + (warnings === 1 ? " source warning" : " source warnings") : "",
  ].filter(Boolean).join(" · ");
  $("footer-stamp").textContent = "Last scan " + ago(snapshot.generated_at) + " · " + snapshot.stats.signals + " relevant signals";

  // A hosted deployment may have nowhere to write a snapshot. Say so on the control
  // rather than letting a click start a scan that cannot be saved.
  const scanState = (state.data && state.data.state) || {};
  const canScan = scanState.writable !== false;
  $("run-scan").title = canScan
    ? ""
    : "This deployment is read-only. Run the scan locally or connect Blob storage to the hosting project.";

  renderKpis(snapshot);
  renderThemes(snapshot);
  renderTopics(snapshot);
  renderIntent(snapshot);
  renderSignals(snapshot);
  renderBrand(snapshot);
}

function renderKpis(snapshot) {
  const rising = snapshot.topics.filter((topic) => topic.momentum === "Rising").length;
  const b2b = snapshot.topics.filter((topic) => topic.audience === "B2B").length;
  const compRows = (state.competitors && Array.isArray(state.competitors.results))
    ? state.competitors.results
    : null;
  const compOpen = compRows ? compRows.filter((row) => row.status === "ok").length : 0;
  const cards = [
    { label: "Signals read", value: snapshot.stats.signals, note: snapshot.stats.outlets + " outlets" },
    { label: "Themes live", value: snapshot.stats.themes, note: snapshot.topics.length + " publishable topics" },
    { label: "Rising", value: rising, note: rising ? "vs last scan" : "baseline scan" },
    {
      label: "Search intents",
      value: snapshot.stats.queries,
      note: (snapshot.demand_summary && snapshot.demand_summary.with_data)
        ? snapshot.demand_summary.with_data + " with volume data"
        : "autocomplete queries",
    },
    {
      label: "Brand mentions",
      value: snapshot.brand.total_mentions,
      note: snapshot.brand.total_mentions
        ? snapshot.brand.share_of_voice + "% share of voice"
        : "no earned coverage yet",
    },
    {
      label: "Competitors tracked",
      value: compRows ? compRows.length : "—",
      note: compRows
        ? compOpen + " reachable · " + (compRows.length - compOpen) + " unreachable"
        : "audit not loaded",
    },
  ];
  $("kpis").innerHTML = cards.map((card) => `
    <div class="kpi">
      <span>${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
      <small>${escapeHtml(card.note)}</small>
    </div>`).join("");
}

function renderThemes(snapshot) {
  const select = $("theme-filter");
  const current = state.theme;
  select.innerHTML = `<option value="all">All themes</option>` + snapshot.themes.map((theme) =>
    `<option value="${escapeHtml(theme.id)}">${escapeHtml(theme.label)} (${theme.count})</option>`).join("");
  select.value = current;
  if (select.value !== current) {
    state.theme = "all";
    select.value = "all";
  }
}

function visibleTopics(snapshot) {
  let topics = snapshot.topics.slice();
  if (state.audience !== "All") {
    topics = topics.filter((topic) => topic.audience === state.audience || topic.audience === "Both");
  }
  if (state.theme !== "all") {
    topics = topics.filter((topic) => topic.theme === state.theme);
  }
  if (state.sort === "momentum") {
    const order = { Rising: 0, New: 1, Steady: 2, Cooling: 3 };
    topics.sort((a, b) => (order[a.momentum] - order[b.momentum]) || (b.change_pct || 0) - (a.change_pct || 0));
  } else if (state.sort === "signals") {
    topics.sort((a, b) => b.signal_count - a.signal_count);
  } else {
    topics.sort((a, b) => b.score - a.score);
  }
  return topics;
}

function renderTopics(snapshot) {
  const topics = visibleTopics(snapshot);
  if (!topics.length) {
    $("topic-grid").innerHTML = `<div class="empty" style="grid-column:1/-1">No topics match this filter. Try “All”.</div>`;
    return;
  }
  $("topic-grid").innerHTML = topics.map((topic, index) => {
    const keywords = topic.keywords.slice(0, 5).map((keyword) =>
      `<span class="chip">${escapeHtml(keyword.query)}<em>${escapeHtml(keyword.stage)}</em></span>`).join("");
    const signals = topic.signals.slice(0, 3).map((signal) => `
      <a href="${escapeHtml(signal.url)}" target="_blank" rel="noopener">
        <span>${escapeHtml(signal.outlet)}</span>${escapeHtml(signal.title)}
      </a>`).join("");
    const brief = topic.brief;
    return `
    <article class="topic" data-topic="${escapeHtml(topic.id)}">
      <div class="topic-head">
        <span class="rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="pill ${topic.audience === "B2C" ? "b2c" : topic.audience === "B2B" ? "b2b" : ""}">${escapeHtml(topic.audience)}</span>
        ${momentumPill(topic)}
        <span class="score" style="--pct:${topic.score}"><b>${topic.score}</b></span>
      </div>
      <h3>${escapeHtml(topic.title)}</h3>
      <div class="meta">${escapeHtml(topic.theme_label)} · ${topic.signal_count} signals · ${topic.outlet_count} outlets · ${topic.query_count} search intents</div>
      <p class="why">${escapeHtml(topic.why_now)}</p>
      <div class="chips">${keywords}</div>
      <div class="signal-list">${signals}</div>
      <div class="brief hidden">
        <h4>Hook</h4>
        <blockquote>${escapeHtml(brief.hook)}</blockquote>
        <div>
          <h4>Angle</h4>
          <p class="why">${escapeHtml(brief.angle)}</p>
        </div>
        <div>
          <h4>Outline filling ${escapeHtml(brief.words)}</h4>
          <ol>${brief.outline.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>
        </div>
        <div class="row"><span>Format</span><span>${escapeHtml(brief.format)}</span></div>
        <div class="row"><span>Call to action</span><span>${escapeHtml(brief.cta)}</span></div>
      </div>
      <div class="topic-actions">
        <button class="ghost" data-action="brief">Content brief</button>
        <button class="ghost" data-action="copy">Copy brief</button>
      </div>
    </article>`;
  }).join("");
}

function demandCells(keyword) {
  const demand = keyword.demand;
  if (!demand || !demand.volume) {
    return `<td class="muted">—</td><td class="muted">—</td><td class="num muted">—</td>`;
  }
  const bid = demand.bid_high != null
    ? `₹${Math.round(demand.bid_low)}–${Math.round(demand.bid_high)}`
    : "—";
  return `<td>${escapeHtml(demand.volume)}</td>
      <td class="muted">${escapeHtml(demand.competition || "—")}</td>
      <td class="num muted">${bid}</td>`;
}

function renderIntent(snapshot) {
  const summary = snapshot.demand_summary || {};
  const note = $("intent-note");
  if (note) {
    note.textContent = summary.with_data
      ? `Volume, competition and top-of-page bids from Google Keyword Planner (${summary.country || "IN"}, trailing 12 months). ${summary.with_data} of ${summary.total} queries have data — the rest show an em dash rather than a guess.`
      : "No keyword data imported yet. Run: python3 -m radar.keywords import <export.csv> --country IN";
  }

  const rows = snapshot.keywords.slice();
  if (state.intentSort === "volume") {
    rows.sort((a, b) => ((b.demand && b.demand.bucket_low) || 0) - ((a.demand && a.demand.bucket_low) || 0) || b.score - a.score);
  } else if (state.intentSort === "score") {
    rows.sort((a, b) => b.score - a.score);
  } else {
    rows.sort((a, b) => (b.demand_score || 0) - (a.demand_score || 0) || b.score - a.score);
  }

  $("intent-body").innerHTML = rows.slice(0, 80).map((keyword) => `
    <tr>
      <td>${escapeHtml(keyword.title)}${keyword.note ? `<div class="muted" style="margin-top:3px">${escapeHtml(keyword.note)}</div>` : ""}</td>
      <td class="muted">${escapeHtml(keyword.theme_label)}</td>
      <td>${escapeHtml(keyword.stage)}</td>
      ${demandCells(keyword)}
      <td class="num"><span class="bar"><i style="width:${keyword.score}%"></i></span> <span class="muted">${keyword.score}</span></td>
      <td class="muted">${escapeHtml(keyword.page_type)}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="muted" style="padding:24px">No search intents collected yet.</td></tr>`;
}

function renderSignals(snapshot) {
  const items = snapshot.signals.slice(0, 60).map((signal) => `
    <div class="feed-item">
      <time>${escapeHtml(shortDate(signal.published))}</time>
      <a href="${escapeHtml(signal.url)}" target="_blank" rel="noopener">${escapeHtml(signal.title)}</a>
      <span class="src">${escapeHtml(signal.outlet)} · ${escapeHtml(signal.theme_label || "—")} · ${escapeHtml(signal.audience)}</span>
    </div>`).join("");
  $("signal-feed").innerHTML = items || `<div class="empty">No signals collected yet.</div>`;
}

function renderBrand(snapshot) {
  const brand = snapshot.brand;
  const competitors = brand.competitors.length
    ? brand.competitors.map((entry) => `
        <tr>
          <td>${escapeHtml(entry.term)}</td>
          <td class="num">${entry.count}</td>
          <td class="muted">${entry.headlines.length ? `<a href="${escapeHtml(entry.headlines[0].url)}" target="_blank" rel="noopener" style="text-decoration:none">${escapeHtml(entry.headlines[0].title)}</a>` : "—"}</td>
        </tr>`).join("")
    : `<tr><td colspan="3" class="muted" style="padding:20px">No competitor coverage found this window.</td></tr>`;

  const mentions = brand.entries.length && brand.entries.some((entry) => entry.count)
    ? brand.entries.flatMap((entry) => entry.headlines.map((headline) => `
        <li><a href="${escapeHtml(headline.url)}" target="_blank" rel="noopener" style="text-decoration:none">${escapeHtml(headline.title)}</a> <span class="muted">· ${escapeHtml(headline.source)}</span></li>`)).join("")
    : `<li>Nothing yet — this is the gap to close.</li>`;

  const outlets = brand.top_outlets.length
    ? brand.top_outlets.map((item) => `${escapeHtml(item.outlet)} (${item.stories})`).join(" · ")
    : "—";

  $("brand-body").innerHTML = `
    <div class="brand-grid">
      <div class="card">
        <h2>Your brand in the press</h2>
        <div class="big-number">${brand.total_mentions}</div>
        <div class="muted">mentions of ZVDapp found in news search · ${brand.share_of_voice}% share of voice vs the brands below</div>
        <p style="margin-top:16px">${escapeHtml(brand.verdict)}</p>
        <ul>${mentions}</ul>
      </div>
      <div class="card">
        <h2>What to do with this</h2>
        <ul>
          <li>Publish this week's highest-scoring topic — it already has proven search demand behind it.</li>
          <li>Pitch the outlets below with a data angle: they are already writing about your category.</li>
          <li>Open a trade briefing page so B2B buyers find you by term, not by ad.</li>
          <li>Claim every 'vs' comparison your competitors appear in — that is free, high-intent traffic.</li>
        </ul>
        <h2 style="margin-top:22px">Outlets covering your category now</h2>
        <p class="muted">${outlets}</p>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <h2>Competitor coverage (same window)</h2>
      <div class="table-wrap" style="border:0;background:none">
        <table class="table">
          <thead><tr><th>Brand</th><th class="num">Mentions</th><th>Most recent story</th></tr></thead>
          <tbody>${competitors}</tbody>
        </table>
      </div>
    </div>`;
}

/* ---------- competitors ---------- */
async function loadCompetitors() {
  try {
    const response = await fetch("/api/competitors", { cache: "no-store" });
    const payload = await response.json();
    state.competitors = payload.data;
    state.compState = payload.state || {};
    renderCompetitors();
    if (state.data && state.data.snapshot) renderKpis(state.data.snapshot);
  } catch (error) {
    $("competitor-body").innerHTML = `<div class="empty">Could not load the competitor audit: ${escapeHtml(error.message)}</div>`;
  }
}

async function runCompetitorAudit() {
  state.compState = { running: true };
  renderCompetitors();
  try {
    await fetch("/api/competitors/audit", { method: "POST" });
  } catch (error) {
    $("competitor-body").innerHTML = `<div class="empty">Could not start the audit: ${escapeHtml(error.message)}</div>`;
    return;
  }
  pollCompetitors();
}

function pollCompetitors() {
  clearTimeout(state.compPoll);
  state.compPoll = setTimeout(async () => {
    await loadCompetitors();
    if (state.compState && state.compState.running) pollCompetitors();
  }, 3000);
}

function statusPill(status) {
  if (status === "blocked") return `<span class="pill cooling">blocked</span>`;
  if (status === "error") return `<span class="pill">unreachable</span>`;
  if (status === "deferred") return `<span class="pill cooling">not read</span>`;
  return `<span class="pill rising">reachable</span>`;
}

function renderCompetitors() {
  const node = $("competitor-body");
  if (!node) return;
  if (state.compState && state.compState.running) {
    node.innerHTML = `<div class="empty"><span class="dot"></span> Auditing competitor sites — sitemaps, schema and stacks. About a minute.</div>`;
    return;
  }
  const data = state.competitors;
  if (!data) {
    node.innerHTML = `<div class="empty">No competitor audit yet.<br><br><button class="ghost" onclick="runCompetitorAudit()">Run the first audit</button></div>`;
    return;
  }
  const blocked = data.results.filter((row) => row.status !== "ok").length;
  const measured = data.results.filter((row) => row.status === "ok");
  const deepest = measured.slice().sort((a, b) => b.content_urls - a.content_urls)[0];
  const rows = data.results.map((row, index) => {
    const evidence = [
      row.title ? `<div><strong>Page title:</strong> ${escapeHtml(row.title)}</div>` : "",
      row.notes.length ? `<div><strong>Notes:</strong> ${row.notes.map(escapeHtml).join(" · ")}</div>` : "",
      row.tech.length ? `<div><strong>Stack signals:</strong> ${row.tech.map(escapeHtml).join(", ")}</div>` : "",
      row.schema.length ? `<div><strong>Schema:</strong> ${escapeHtml(row.schema.join(", "))}</div>` : "",
      row.sitemap_children ? `<div><strong>Sitemaps:</strong> ${row.sitemap_children} in index · newest update ${escapeHtml(row.newest_lastmod || "unknown")}</div>` : "",
      `<div><strong>Sampled URLs:</strong> ${row.total_urls} (${row.content_urls} content · ${row.product_urls} catalogue · ${row.other_urls} other)</div>`,
    ].filter(Boolean).join("");
    return `
      <tr>
        <td class="muted">${index + 1}</td>
        <td><strong>${escapeHtml(row.name)}</strong><div class="muted">${escapeHtml(row.type)} · ${escapeHtml(row.market)}</div></td>
        <td class="num"><span class="bar"><i style="width:${row.score}%"></i></span> <span class="muted">${row.score}</span></td>
        <td class="num">${row.content_urls}</td>
        <td class="num">${row.product_urls}</td>
        <td class="num">${row.updated_90d}</td>
        <td class="muted">${row.tech.length ? escapeHtml(row.tech.slice(0, 3).join(", ")) : "—"}</td>
        <td>${statusPill(row.status)}</td>
      </tr>
      <tr class="detail-row">
        <td></td>
        <td colspan="7"><details><summary>Evidence</summary><div class="evidence">${evidence}</div></details></td>
      </tr>`;
  }).join("");

  node.innerHTML = `
    <div class="kpis" style="margin:0 0 18px">
      <div class="kpi"><span>Audited</span><strong>${data.count}</strong><small>${blocked} block crawlers</small></div>
      <div class="kpi"><span>Deepest content</span><strong>${deepest ? deepest.content_urls : 0}</strong><small>${deepest ? escapeHtml(deepest.name) : "—"} pages</small></div>
      <div class="kpi"><span>Highest score</span><strong>${measured.length ? measured[0].score : 0}</strong><small>${measured.length ? escapeHtml(measured[0].name) : "—"}</small></div>
      <div class="kpi"><span>Updated last 90d</span><strong>${measured.reduce((sum, row) => sum + row.updated_90d, 0)}</strong><small>pages across the set</small></div>
      <div class="kpi"><span>Last run</span><strong>${escapeHtml((data.generated_at || "").slice(0, 10))}</strong><small>${state.compState.seconds ? state.compState.seconds + "s" : "public evidence"}</small></div>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th></th><th>Competitor</th><th class="num">Presence</th><th class="num">Content</th><th class="num">Catalogue</th><th class="num">New 90d</th><th>Stack signals</th><th>Access</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="panel-note" style="margin-top:14px">Presence score is a labelled heuristic (content volume, content-to-catalogue depth, schema, social proof, retention and experience tools, freshness) used to rank — not a traffic estimate. ${blocked} sites refuse non-browser clients, so they are marked blocked rather than scored.</p>`;
}

/* ---------- competitor publishing ---------- */
async function loadPublishing() {
  try {
    const response = await fetch("/api/publishing", { cache: "no-store" });
    const payload = await response.json();
    state.publishing = payload.data;
    state.pubState = payload.state || {};
    renderPublishing();
  } catch (error) {
    const node = $("publishing-body");
    if (node) node.innerHTML = `<div class="empty">Could not load competitor publishing: ${escapeHtml(error.message)}</div>`;
  }
}

async function runPublishing() {
  state.pubState = { running: true };
  renderPublishing();
  try {
    await fetch("/api/publishing", { method: "POST" });
  } catch (error) {
    $("publishing-body").innerHTML = `<div class="empty">Could not start the collection: ${escapeHtml(error.message)}</div>`;
    return;
  }
  pollPublishing();
}

function pollPublishing() {
  clearTimeout(state.pubPoll);
  state.pubPoll = setTimeout(async () => {
    await loadPublishing();
    if (state.pubState && state.pubState.running) pollPublishing();
  }, 3000);
}

function publishingRow(entry) {
  const items = entry.new.map((item) => `
    <li><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title || item.url)}</a>
      <span class="muted">· ${escapeHtml(item.kind)}${item.lastmod ? " · " + escapeHtml(item.lastmod) : ""}</span></li>`).join("");
  const feeds = entry.rss.map((item) => `
    <li><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
      <span class="muted">· feed${item.published ? " · " + escapeHtml(item.published.slice(0, 16)) : ""}</span></li>`).join("");
  const body = [
    items ? `<div><strong>${entry.first_run ? "Most recently updated pages" : "New since last run"}</strong><ul>${items}</ul></div>` : "",
    feeds ? `<div><strong>From their blog feed</strong><ul>${feeds}</ul></div>` : "",
    entry.source === "crawl" ? `<div><strong>How this was found:</strong> they publish no sitemap, so pages come from their own navigation links.</div>` : "",
    entry.note ? `<div class="muted">${escapeHtml(entry.note)}</div>` : "",
    entry.error ? `<div><strong>Could not read their sitemap:</strong> ${escapeHtml(entry.error)}</div>` : "",
  ].filter(Boolean).join("");
  return `
    <tr>
      <td><strong>${escapeHtml(entry.name)}</strong><div class="muted">${escapeHtml(entry.type)} · ${escapeHtml(entry.market)}</div></td>
      <td class="num">${entry.total_urls}</td>
      <td class="num">${entry.content_urls}</td>
      <td class="num"><strong>${entry.new_count}</strong></td>
      <td class="muted">${entry.rss.length ? entry.rss.length + " feed items" : "—"}</td>
      <td>${statusPill(entry.status)}</td>
    </tr>
    <tr class="detail-row"><td></td><td colspan="5">${
      body ? `<details><summary>What they published</summary><div class="evidence">${body}</div></details>`
           : `<span class="muted">Nothing new collected.</span>`}</td></tr>`;
}

function renderPublishing() {
  const node = $("publishing-body");
  if (!node) return;
  if (state.pubState && state.pubState.running) {
    node.innerHTML = `<div class="empty"><span class="dot"></span> Reading competitor sitemaps and feeds — about a minute.</div>`;
    return;
  }
  const data = state.publishing;
  if (!data) {
    node.innerHTML = `<div class="empty">No publishing snapshot yet.<br><br><button class="ghost" onclick="runPublishing()">Collect competitor output</button></div>`;
    return;
  }
  const feeds = data.domains.filter((entry) => entry.rss.length).length;
  node.innerHTML = `
    <div class="kpis" style="margin:0 0 18px">
      <div class="kpi"><span>Reachable</span><strong>${data.reachable}</strong><small>of ${data.count} tracked</small></div>
      <div class="kpi"><span>New pages</span><strong>${data.total_new}</strong><small>${data.baseline ? "first baseline run" : "since last run"}</small></div>
      <div class="kpi"><span>Live feeds</span><strong>${feeds}</strong><small>blog RSS working</small></div>
      <div class="kpi"><span>Collected</span><strong>${escapeHtml((data.generated_at || "").slice(0, 10))}</strong><small>${data.seconds ? data.seconds + "s" : ""}</small></div>
    </div>
    <div class="table-wrap">
      <table class="table">
        <thead><tr><th>Competitor</th><th class="num">URLs</th><th class="num">Content</th><th class="num">New</th><th>Feeds</th><th>Access</th></tr></thead>
        <tbody>${data.domains.map(publishingRow).join("")}</tbody>
      </table>
    </div>
        <p class="panel-note" style="margin-top:14px">${data.baseline
      ? "First run, so there is nothing to diff against yet — each competitor shows its most recently updated pages instead of claiming everything is new. The next run reports genuine additions."
      : "New pages are URLs present now that were absent at the last run, read from each site's own sitemap. Titles are fetched for a few of them; a page we cannot read keeps its URL rather than a guess."
    }</p>`;
}

/* ---------- battlecards ---------- */
function renderBattlecards() {
  const node = $("battlecards-body");
  if (!node) return;
  const arr = (value) => (Array.isArray(value) ? value : []);
  const txt = (value) => (value == null || value === "" ? "not captured" : value);
  
  // Load battlecard data from API
  fetch("/api/battlecards", { cache: "no-store" })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((payload) => {
      const cards = payload.cards || {};
      let html = "";
      
      // VDB card
      if (cards.vdb) {
        const s = cards.vdb.index_snapshot || {};
        html += `
          <div class="battlecard" style="border:2px solid #e53e3e; margin-bottom:24px">
            <div class="battlecard-header" style="background:#e53e3e; color:white; padding:12px; font-weight:bold;">
              ZVD vs Virtual Diamond Boutique
            </div>
            <div class="battlecard-body" style="padding:16px">
              <div class="battlecard-section" style="margin-bottom:12px">
                <strong>Status:</strong> ${cards.vdb.status}<br>
                <strong>Scale:</strong> ${s.scale_claims || "No data"}<br>
                <strong>Pricing:</strong> ${s.pricing_marketplace || "No data"}<br>
                <strong>Founder note:</strong> ${s.founder_note || "No data"}<br>
                <strong>Contact:</strong> ${s.contact || "No data"}<br>
                <strong>Google Play:</strong> ${s.google_play || "No data"}<br>
              </div>
              <div class="battlecard-section" style="border-top:1px solid #eee; padding-top:8px; margin-top:8px">
                <strong>Wedge:</strong> ${txt(cards.vdb.wedge)}<br>
                <strong>Target queries:</strong> ${arr(cards.vdb.target_queries).join(", ") || "not captured"}<br>
                <strong>Notes:</strong> ${arr(cards.vdb.notes).join(" · ")}<br>
              </div>
            </div>
          </div>
        `;
      }
      
      // DND card
      if (cards.dnd) {
        html += `
          <div class="battlecard" style="border:2px solid #7f5af0; margin-bottom:24px">
            <div class="battlecard-header" style="background:#7f5af0; color:white; padding:12px; font-weight:bold;">
              ZVD vs DND Diamond
            </div>
            <div class="battlecard-body" style="padding:16px">
              <div class="battlecard-section" style="margin-bottom:12px">
                <strong>Status:</strong> ${cards.dnd.status}<br>
                <strong>Score:</strong> ${cards.dnd.score}<br>
                <strong>Product URLs:</strong> ${cards.dnd.product_urls}<br>
                <strong>Content URLs:</strong> ${cards.dnd.content_urls}<br>
              </div>
              <div class="battlecard-section" style="border-top:1px solid #eee; padding-top:8px; margin-top:8px">
                <strong>Wedge:</strong> ${txt(cards.dnd.wedge)}<br>
                <strong>Target queries:</strong> ${arr(cards.dnd.target_queries).join(", ") || "not captured"}<br>
                <strong>Notes:</strong> ${arr(cards.dnd.notes).join(" · ")}<br>
              </div>
            </div>
          </div>
        `;
      }
      
      // Lepdo card
      if (cards.lepdo) {
        html += `
          <div class="battlecard" style="border:2px solid #18bc9c; margin-bottom:24px">
            <div class="battlecard-header" style="background:#18bc9c; color:white; padding:12px; font-weight:bold;">
              ZVD vs Lepdo Diamonds
            </div>
            <div class="battlecard-body" style="padding:16px">
              <div class="battlecard-section" style="margin-bottom:12px">
                <strong>Status:</strong> ${cards.lepdo.status}<br>
                <strong>Score:</strong> ${cards.lepdo.score}<br>
                <strong>Total URLs:</strong> ${cards.lepdo.total_urls}<br>
                <strong>Content URLs:</strong> ${cards.lepdo.content_urls}<br>
                <strong>Product URLs:</strong> ${cards.lepdo.product_urls}<br>
              </div>
              <div class="battlecard-section" style="border-top:1px solid #eee; padding-top:8px; margin-top:8px">
                <strong>Wedge:</strong> ${txt(cards.lepdo.wedge)}<br>
                <strong>Target queries:</strong> ${arr(cards.lepdo.target_queries).join(", ") || "not captured"}<br>
                <strong>Notes:</strong> ${arr(cards.lepdo.notes).join(" · ")}<br>
              </div>
            </div>
          </div>
        `;
      }
      
      if (Object.keys(cards).length === 0) {
        node.innerHTML = `<div class="empty">No battlecard data loaded. Generating…</div>`;
      } else {
        node.innerHTML = html;
      }
    })
    .catch((e) => {
      console.error(e);
      node.innerHTML = `<div class="empty">Could not load battlecards: ${e.message}</div>`;
    });
}

/* ---------- brief text ---------- */
function briefText(topic) {
  const brief = topic.brief;
  return [
    "ZVD RADAR — CONTENT BRIEF",
    "Date: " + (state.data.snapshot ? state.data.snapshot.date : ""),
    "Topic: " + topic.title,
    "Theme: " + topic.theme_label + " · Audience: " + topic.audience + " · Opportunity score: " + topic.score,
    "",
    "WHY NOW",
    topic.why_now,
    "",
    "HOOK",
    brief.hook,
    "",
    "ANGLE",
    brief.angle,
    "",
    "OUTLINE (" + brief.words + ")",
    brief.outline.map((line, index) => (index + 1) + ". " + line).join("\n"),
    "",
    "FORMAT: " + brief.format,
    "CTA: " + brief.cta,
    "",
    "TARGET QUERIES",
    topic.keywords.map((keyword) => "· " + keyword.query + " (" + keyword.stage + ", " + keyword.score + ")").join("\n"),
    "",
    "SOURCE SIGNALS",
    topic.signals.map((signal) => "· " + signal.title + " — " + signal.outlet + (signal.published ? " (" + signal.published.slice(0, 10) + ")" : "")).join("\n"),
  ].join("\n");
}

/* ---------- events ---------- */
document.addEventListener("click", (event) => {
  const tab = event.target.closest(".tab");
  if (tab) {
    state.tab = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((node) => node.classList.toggle("is-active", node === tab));
    document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("hidden", panel.id !== "panel-" + state.tab));
    if (state.tab === "competitors") {
      renderCompetitors();
      renderPublishing();
    }
    if (state.tab === "battlecards") {
      renderBattlecards();
    }
    return;
  }

  const seg = event.target.closest(".seg");
  if (seg) {
    state.audience = seg.dataset.audience;
    document.querySelectorAll("#audience-filter .seg").forEach((node) => node.classList.toggle("is-active", node === seg));
    if (state.data && state.data.snapshot) renderTopics(state.data.snapshot);
    return;
  }

  const action = event.target.closest("[data-action]");
  if (action) {
    const card = action.closest(".topic");
    const snapshot = state.data && state.data.snapshot;
    if (!card || !snapshot) return;
    const topic = snapshot.topics.find((item) => item.id === card.dataset.topic);
    if (!topic) return;
    if (action.dataset.action === "brief") {
      const brief = card.querySelector(".brief");
      brief.classList.toggle("hidden");
      action.textContent = brief.classList.contains("hidden") ? "Content brief" : "Hide brief";
    } else {
      navigator.clipboard.writeText(briefText(topic)).then(() => {
        action.textContent = "Copied ✓";
        setTimeout(() => { action.textContent = "Copy brief"; }, 1600);
      });
    }
    return;
  }

  if (event.target.id === "run-scan") {
    runScan();
  }

  if (event.target.id === "run-competitors") {
    runCompetitorAudit();
  }

  if (event.target.id === "run-publishing") {
    runPublishing();
  }
});

$("theme-filter").addEventListener("change", (event) => {
  state.theme = event.target.value;
  if (state.data && state.data.snapshot) renderTopics(state.data.snapshot);
});

$("sort-filter").addEventListener("change", (event) => {
  state.sort = event.target.value;
  if (state.data && state.data.snapshot) renderTopics(state.data.snapshot);
});

$("intent-sort").addEventListener("change", (event) => {
  state.intentSort = event.target.value;
  if (state.data && state.data.snapshot) renderIntent(state.data.snapshot);
});

load();
loadCompetitors();
loadPublishing();
setInterval(() => {
  const scan = state.data && state.data.state;
  if (!scan || !scan.running) load();
}, 60000);
