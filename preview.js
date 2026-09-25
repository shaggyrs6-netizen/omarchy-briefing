"use strict";
let state, busy = false, view = "updates";
const $ = id => document.getElementById(id);
const date = value => value ? new Date(value).toLocaleString(undefined, {dateStyle:"medium", timeStyle:"short"}) : "Never";
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function link(text, url) {
  const el = node("a", text); el.href = url; el.target = "_blank"; el.rel = "noopener noreferrer"; return el;
}
async function request(payload) {
  if (busy) return;
  busy = true; $("error").hidden = true;
  document.querySelectorAll("button").forEach(x => x.disabled = true);
  try {
    const response = await fetch(payload ? "/api/action" : "/api/status", payload ? {
      method:"POST", headers:{"Content-Type":"application/json", "X-Briefing-Token":state.token}, body:JSON.stringify(payload)
    } : {});
    const data = await response.json();
    if (!response.ok || data.error) throw Error(data.error || "Request failed");
    state = data; render();
  } catch (error) {
    $("error").textContent = error.message; $("error").hidden = false;
  } finally {
    busy = false; document.querySelectorAll("button").forEach(x => x.disabled = false);
  }
}
function renderUpdates() {
  const container = $("updates"); container.replaceChildren();
  $("coverage").textContent = state.coverage;
  const mise = state.mise || {installed:[], history:[]};
  container.append(node("h3", "Installed tools · mise"));
  if (mise.error) container.append(node("p", mise.error + " Saved observations may be stale.", "warning"));
  container.append(node("p", "Checked " + date(mise.checkedAt) + ". First seen is when Briefing noticed a version, not its installation time.", "hint"));
  for (const item of mise.installed.filter(x => x.active)) {
    const card = node("article", undefined, "card");
    card.append(node("h3", item.title), node("p", item.version, "version"), node("p", item.description, "description"), node("p", "Selected in home configuration · " + (item.baseline ? "Existing installation discovered" : "New installation observed") + " · first seen " + date(item.firstSeen), "hint"));
    container.append(card);
  }
  for (const item of mise.history.slice(0,20)) container.append(node("p", `${item.title} ${item.version} · ${item.event} · observed between ${date(item.since)} and ${date(item.at)}`, "hint"));
  container.append(node("h3", "Package transactions"));
  if (state.logError) container.append(node("p", state.logError, "warning"));
  const latest = state.transactions[0]?.started.slice(0,10);
  const txs = state.transactions.filter(tx => $("date-filter").value === "all" || tx.started.slice(0,10) === latest);
  if (!txs.length) container.append(node("p", "No recorded package changes found.", "empty"));
  for (const tx of txs) {
    const group = node("div", undefined, "transaction");
    group.append(node("p", `${date(tx.started)} · ${tx.status} · ${tx.changes.length} package${tx.changes.length === 1 ? "" : "s"}`));
    if (!tx.completed) group.append(node("p", "This transaction has no completion record. Its changes are not presented as a completed update.", "warning"));
    for (const change of tx.changes) {
      const card = node("article", undefined, "card");
      const top = node("div", undefined, "card-top");
      top.append(node("h3", change.title), node("span", change.action, "tag")); card.append(top);
      card.append(node("p", change.description, "description"));
      const versions = change.oldVersion && change.newVersion && change.oldVersion !== change.newVersion ? `${change.oldVersion} → ${change.newVersion}` : change.newVersion || change.oldVersion;
      card.append(node("p", versions, "version"), node("p", change.changeKind, "hint"));
      const details = node("details"); details.append(node("summary", "Changes, sources & evidence"));
      details.append(node("p", change.releaseNote), node("p", change.actionNote, "hint"));
      if (change.releaseUrl) {details.append(link("Read this release announcement ↗", change.releaseUrl)); details.append(node("p", change.releaseScope, "hint"));}
      else if (change.sourceUrl) details.append(link("Browse source · not matched to this version ↗", change.sourceUrl));
      details.append(node("pre", `${state.logPath}:${change.line}\n${change.evidence}`));
      card.append(details); group.append(card);
    }
    for (const rebuild of tx.rebuilds) {
      const card = node("article", undefined, "card"); card.append(node("h3", "Driver rebuild recorded"), node("p", rebuild.description, "description"));
      const details = node("details"); details.append(node("summary", "Show evidence"), node("pre", `${state.logPath}:${rebuild.line}\n${rebuild.evidence}`)); card.append(details); group.append(card);
    }
    container.append(group);
  }
}
function shownNews() {
  return state.news.filter(item => (!$("official-only").checked || ["official","releases"].includes(item.source)) && (!$("unread-only").checked || !item.read));
}
function renderNews() {
  $("unread").textContent = state.unread;
  $("source-status").replaceChildren();
  if (state.newsError) $("source-status").append(node("p", state.newsError, "failed"));
  for (const source of state.sources.filter(x => x.enabled)) {
    $("source-status").append(node("div", `${source.name} · last successful check: ${date(source.lastSuccess)}${source.error ? " · " + source.error : ""}`, source.error ? "failed" : ""));
  }
  const container = $("news"); container.replaceChildren();
  const items = shownNews();
  if (!items.length) container.append(node("p", state.news.length ? "You’re caught up with this view." : "No saved headlines yet. Choose your sources in Settings, then refresh news.", "empty"));
  for (const item of items) {
    const card = node("article", undefined, "card news-card" + (item.read ? " read" : ""));
    card.append(node("div", `${item.label} · ${item.published ? date(item.published) : "Date unavailable"}${item.read ? " · Read" : " · Unread"}`, "news-meta"), node("h3", item.title), node("p", item.excerpt, "description"));
    const actions = node("div", undefined, "actions");
    const sourceLink = link("Read original ↗", item.url);
    sourceLink.addEventListener("click", () => request({action:"read", ids:[item.id], read:true}));
    const mark = node("button", item.read ? "Mark unread" : "Mark read");
    mark.addEventListener("click", () => request({action:"read", ids:[item.id], read:!item.read}));
    actions.append(sourceLink, mark); card.append(actions); container.append(card);
  }
}
function renderSettings() {
  $("interval").value = state.settings.intervalHours;
  $("sources").replaceChildren();
  for (const source of state.sources) {
    const label = node("label"); const input = node("input"); input.type = "checkbox"; input.value = source.id; input.checked = source.enabled;
    label.append(input, document.createTextNode(source.name), node("small", source.label)); $("sources").append(label);
  }
}
function render() {
  renderUpdates(); renderNews();
  // Leave unsaved controls intact during background checks.
  if (view !== "settings") renderSettings();
  $("checked").textContent = "History read " + date(state.generatedAt);
}
for (const name of ["updates", "news", "settings"]) $(name + "-tab").onclick = () => {
  view = name;
  for (const other of ["updates", "news", "settings"]) {
    $(other + "-view").hidden = other !== name;
    $(other + "-tab").classList.toggle("active", other === name);
    $(other + "-tab").setAttribute("aria-pressed", String(other === name));
  }
  if (name === "settings" && state) renderSettings();
};
$("date-filter").onchange = renderUpdates;
$("official-only").onchange = renderNews;
$("unread-only").onchange = renderNews;
$("refresh").onclick = () => request({action:"refresh", force:true});
$("read-all").onclick = () => request({action:"read", ids:shownNews().map(x => x.id), read:true});
$("read-everything").onclick = () => request({action:"read", ids:state.news.map(x => x.id), read:true});
$("save").onclick = async () => {
  const settings = {intervalHours:Number($("interval").value), enabledSources:[...$("sources").querySelectorAll("input:checked")].map(x => x.value)};
  await request({action:"settings", settings});
  if ($("error").hidden) $("saved").textContent = "Saved on this computer";
};
request().then(() => {if (state?.settings.intervalHours) request({action:"refresh", force:false});});
setInterval(() => {if (state?.settings.intervalHours && !busy && view !== "settings") request({action:"refresh", force:false});}, 60000);
