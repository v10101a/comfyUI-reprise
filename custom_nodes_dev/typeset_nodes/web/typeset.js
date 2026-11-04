// Reprise inside ComfyUI: a sidebar tab (projects, recent footage from this graph, import this graph as a
// workflow), "open in Reprise" on any node that produced a video or a song, and "add to <project>" (the
// project last opened in the studio) for videos and images. The studio itself is at /typeset/.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const STUDIO = "/typeset/";
const VIDEO = /\.(mp4|webm|mov|mkv|m4v)$/i;
const AUDIO = /\.(wav|flac|mp3|m4a|ogg|opus)$/i;
const IMAGE = /\.(png|jpe?g|webp)$/i;
const recent = []; // newest first: {filename, subfolder, type, kind, node}
let current = null; // {projectId, name}: the project open in the studio
const byNode = new Map(); // node id -> media from its last execution
let rerender = () => {};

function mediaOf(output) {
  const out = [];
  for (const items of Object.values(output || {})) {
    if (!Array.isArray(items)) continue;
    for (const it of items) {
      if (!it || typeof it.filename !== "string") continue;
      const kind = VIDEO.test(it.filename) ? "video" : AUDIO.test(it.filename) ? "audio" : IMAGE.test(it.filename) ? "image" : null;
      if (kind) out.push({ filename: it.filename, subfolder: it.subfolder || "", type: it.type || "output", kind });
    }
  }
  return out;
}

async function openInTypeset(ref) {
  const tab = window.open("about:blank", "_blank"); // open now: popup blockers allow it inside the click
  try {
    const r = await fetch(`${STUDIO}api/import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(ref) });
    const body = await r.json();
    if (!r.ok) throw new Error(body.detail || r.statusText);
    const url = `${STUDIO}#/studio?project=${encodeURIComponent(body.id)}`;
    if (tab) tab.location.href = url; else window.open(url, "_blank");
  } catch (err) {
    tab?.close();
    toast("error", String(err.message || err), 6000);
  }
}

const toast = (severity, detail, life = 4000) => app.extensionManager?.toast?.add({ severity, summary: "Reprise", detail, life });

async function refreshCurrent() {
  try { const s = await (await fetch(`${STUDIO}api/session`)).json(); current = s?.projectId ? s : null; } catch { current = null; }
  return current;
}

async function post(path, body) {
  const r = await fetch(`${STUDIO}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(out.detail || r.statusText);
  return out;
}

// Land a Comfy output in the project being edited: an asset plus a layer under the text.
async function addToProject(ref) {
  if (!current) return toast("warn", "open a project in the studio first");
  try {
    await post(`api/projects/${encodeURIComponent(current.projectId)}/assets`,
      { comfy: { filename: ref.filename, subfolder: ref.subfolder, type: ref.type }, addLayer: true, source: { node: ref.node } });
    toast("success", `added to ${current.name || "project"}`);
  } catch (err) { toast("error", String(err.message || err), 6000); }
}

// The open graph becomes a Reprise workflow: Comfy's own conversion gives the API form (subgraphs, dynamic widgets).
async function importGraph() {
  try {
    const { output, workflow } = await app.graphToPrompt();
    const name = app.extensionManager?.workflow?.activeWorkflow?.filename || document.title.replace(/[*\s-]*ComfyUI.*$/, "") || "";
    const wf = await post("api/workflows", { name, graph: output, ui: workflow, source: "comfy" });
    toast(wf.missing?.length ? "warn" : "success", wf.missing?.length ? `imported; missing ${wf.missing.join(", ")}` : `imported ${wf.name}`);
  } catch (err) { toast("error", String(err.message || err), 6000); }
}

const CSS = `
.ts-side{--bg:#1b1f11;--p2:#3b4028;--tx:#c7c7c7;--mut:#7d847d;--acc:#b2a2cd;--glow:#949bfb;
  font:12px/1.55 "IBM Plex Mono",ui-monospace,monospace;color:var(--tx);background:var(--bg);min-height:100vh;box-sizing:border-box;overflow:auto;padding:16px 14px}
.ts-side h1{font:400 26px/1 "Newsreader",Georgia,serif;color:var(--acc);margin:0 0 4px}
.ts-side .sub{color:var(--mut);font-style:italic;margin-bottom:14px}
.ts-side .rule{border-top:2px dotted #767676;margin:14px 0 10px}
.ts-side .h{color:var(--mut);font-style:italic;margin-bottom:6px}
.ts-side a,.ts-side button{all:unset;cursor:pointer;color:var(--acc);font-style:italic}
.ts-side a:hover,.ts-side button:hover{font-style:normal;text-shadow:0 0 12px var(--glow)}
.ts-side .open{display:inline-block;padding:4px 0}
.ts-side ul{list-style:none;margin:0;padding:0}
.ts-side li{display:flex;gap:6px;white-space:nowrap}
.ts-side li .t{color:#767676}
.ts-side li .n{overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
.ts-side .acts{display:flex;gap:14px}
.ts-side .empty{color:var(--mut)}
`;

function tree(items, line) {
  if (!items.length) return null;
  const ul = document.createElement("ul");
  items.forEach((it, i) => {
    const li = document.createElement("li");
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = i === items.length - 1 ? "└──" : "├──";
    li.append(t, ...line(it));
    ul.append(li);
  });
  return ul;
}

function el(tag, props = {}, text) {
  const e = Object.assign(document.createElement(tag), props);
  if (text != null) e.textContent = text;
  return e;
}

async function renderSide(root) {
  root.replaceChildren();
  const side = el("div", { className: "ts-side" });
  side.append(el("style", {}, CSS), el("h1", {}, "reprise"), el("div", { className: "sub" }, "a studio for music video and motion graphics"));
  await refreshCurrent();
  const acts = el("div", { className: "acts" });
  acts.append(el("a", { className: "open", href: STUDIO + (current ? `#/studio?project=${encodeURIComponent(current.projectId)}` : ""), target: "_blank" }, "open studio ↗"),
    Object.assign(el("button", { className: "open", title: "use this graph as a Reprise workflow" }, "import graph"), { onclick: importGraph }));
  side.append(acts);

  side.append(el("div", { className: "rule" }), el("div", { className: "h" }, "from this graph/"));
  side.append(tree(recent.slice(0, 8), r => [
    el("span", { className: "n", title: r.filename }, r.filename),
    ...(current && r.kind !== "audio" ? [Object.assign(el("button", { title: `add to ${current.name || "the open project"}` }, "+ add"), { onclick: () => addToProject(r) })] : []),
    ...(r.kind !== "image" ? [Object.assign(el("button", { title: "new project" }, "→ new"), { onclick: () => openInTypeset(r) })] : []),
  ]) || el("div", { className: "empty" }, "run a graph that saves a video, an image or a song; it shows up here."));

  side.append(el("div", { className: "rule" }), el("div", { className: "h" }, "projects/"));
  try {
    const projects = await (await fetch(`${STUDIO}api/projects`)).json();
    side.append(tree(projects.slice(0, 12), p => [
      el("a", { className: "n", href: `${STUDIO}#/studio?project=${encodeURIComponent(p.id)}`, target: "_blank", title: p.name }, p.name.toLowerCase()),
    ]) || el("div", { className: "empty" }, "no projects yet."));
  } catch {
    side.append(el("div", { className: "empty" }, "studio not mounted — see the node pack readme."));
  }
  root.append(side);
}

app.registerExtension({
  name: "typeset.studio",
  async setup() {
    for (const href of ["https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;1,400&family=Newsreader:opsz@6..72&display=swap"]) {
      document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href }));
    }
    refreshCurrent();
    window.addEventListener("focus", refreshCurrent);
    api.addEventListener("executed", ({ detail }) => {
      const media = mediaOf(detail?.output);
      if (media.length) byNode.set(String(detail.display_node ?? detail.node), media);
      for (const m of [...media].reverse()) {
        if (!recent.some(r => r.filename === m.filename && r.subfolder === m.subfolder)) recent.unshift({ ...m, node: detail.node });
      }
      recent.length = Math.min(recent.length, 24);
      rerender();
    });
    app.extensionManager?.registerSidebarTab?.({
      id: "typeset",
      icon: "pi pi-align-left",
      title: "Reprise",
      tooltip: "Reprise — music video and motion graphics",
      type: "custom",
      render: root => { rerender = () => renderSide(root); renderSide(root); },
    });
  },
  getNodeMenuItems(node) {
    const media = (byNode.get(String(node.id)) || []).slice(0, 3);
    const tag = m => (media.length > 1 ? ` · ${m.filename}` : "");
    return [
      ...media.filter(m => m.kind !== "image").map(m => ({ content: `open in Reprise${tag(m)}`, callback: () => openInTypeset(m) })),
      ...(current ? media.filter(m => m.kind !== "audio").map(m => ({ content: `add to ${current.name || "Reprise project"}${tag(m)}`, callback: () => addToProject(m) })) : []),
    ];
  },
});
