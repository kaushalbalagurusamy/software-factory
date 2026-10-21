// Runs the dashboard shell's inline scripts against a stub DOM and canned fetch() responses; prints all rendered text.
const fs = require("fs"), vm = require("vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const cfg = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const all = new Map();
let n = 0;
function el(id) {
  if (!all.has(id)) {
    const o = { id, innerHTML: "", textContent: "", className: "", value: "", style: {}, dataset: {}, _l: {} };
    all.set(id, new Proxy(o, {
      get(t, k) {
        if (k in t) return t[k];
        if (k === "addEventListener") return (e, f) => { (t._l[e] = t._l[e] || []).push(f); };
        if (k === "classList") return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
        return typeof k === "string" ? function () { return null; } : undefined;
      },
      set(t, k, v) { t[k] = v; return true; },
    }));
  }
  return all.get(id);
}
const location = { hash: cfg.hash, search: "", href: "http://localhost/ops/shell/index.html" };
const sandbox = {
  document: { getElementById: el, addEventListener() {}, querySelector: (s) => el("q:" + s), querySelectorAll: () => [],
              createElement: () => el("c" + n++), body: el("body"), documentElement: el("html") },
  location, URLSearchParams, console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
  navigator: { clipboard: { writeText() {} } },
  fetch: (u) => {
    const key = String(u).replace(/^(\.\.\/)+/, "").replace(/^\//, "");
    const v = cfg.files[key];
    if (v === undefined) return Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(v) });
  },
};
sandbox.window = sandbox;
sandbox.addEventListener = () => {};
vm.createContext(sandbox);
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
try { scripts.forEach((s) => vm.runInContext(s, sandbox)); } catch (e) { console.error("script error: " + e.stack); process.exit(3); }
setTimeout(() => {
  const text = [...all.values()].map((e) => String(e.textContent) + "\n" + String(e.innerHTML)).join("\n");
  process.stdout.write(JSON.stringify({ text }));
  process.exit(0);
}, 400);
