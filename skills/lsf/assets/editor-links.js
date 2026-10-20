/* editor-links:begin */
var SFEditorLinks = (function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module && module.exports) { module.exports = api; }
  else if (root) { root.SFEditorLinks = api; }
  return api;
})(typeof window !== "undefined" ? window : null, function () {
  var MAX_PATH = 4096, MAX_LINE = 10000000;
  var EDITORS = ["vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate"];
  function encSeg(s) { return s.split("/").map(encodeURIComponent).join("/"); }
  function encRoot(r) {
    var m = /^([A-Za-z]:)(\/.*)?$/.exec(r);
    return m ? m[1] + encSeg(m[2] || "") : encSeg(r);
  }
  function lineOf(line) {
    var n;
    if (typeof line === "number") { n = line; }
    else if (typeof line === "string" && /^[0-9]+$/.test(line)) { n = parseInt(line, 10); }
    else { return null; }
    if (isFinite(n) && Math.floor(n) === n && n >= 1 && n <= MAX_LINE) { return n; }
    return null;
  }
  function normRoot(r) {
    var n, i, segs, drive;
    if (typeof r !== "string" || r.length === 0 || r.length > MAX_PATH || r.indexOf("\0") >= 0) { return null; }
    drive = /^[A-Za-z]:[\\\/]/.test(r);
    if (!drive && (r.indexOf("\\") >= 0 || r.charAt(0) !== "/")) { return null; }
    n = drive ? r.replace(/\\/g, "/") : r;
    if (n.charAt(n.length - 1) === "/") { n = n.slice(0, -1); }
    segs = n.slice(drive ? 3 : 1).split("/");
    if (n.length === (drive ? 2 : 0)) { return n; }
    for (i = 0; i < segs.length; i++) { if (segs[i] === "" || segs[i] === ".") { return null; } }
    return n;
  }
  function validRoot(r) { return normRoot(r) !== null; }
  function validRel(p) {
    var i, segs;
    if (typeof p !== "string" || p.length === 0 || p.length > MAX_PATH) { return false; }
    if (p.indexOf("\0") >= 0 || p.indexOf("\\") >= 0 || p.charAt(0) === "/") { return false; }
    if (/^[A-Za-z0-9+.\-]+:/.test(p)) { return false; }
    segs = p.split("/");
    for (i = 0; i < segs.length; i++) { if (segs[i] === ".." || segs[i] === "." || segs[i] === "") { return false; } }
    return true;
  }
  function build(editor, rootDir, relPath, line) {
    var base, abs, n, q, i, found = false;
    if (typeof editor !== "string") { return null; }
    for (i = 0; i < EDITORS.length; i++) { if (EDITORS[i] === editor) { found = true; } }
    if (!found || !validRoot(rootDir) || !validRel(relPath)) { return null; }
    base = normRoot(rootDir);
    n = lineOf(line);
    if (editor === "idea") {
      return "idea://open?file=" + encodeURIComponent(base + "/" + relPath) + (n ? "&line=" + n : "");
    }
    abs = encRoot(base) + "/" + encSeg(relPath);
    q = n ? "&line=" + n : "";
    if (editor === "sublime") { return "subl://open?url=file://" + abs + q; }
    if (editor === "textmate") { return "txmt://open?url=file://" + abs + q; }
    return editor + "://file/" + abs.replace(/^\//, "") + (n ? ":" + n : "");
  }
  function editorUrl(editor, rootDir, relPath, line) {
    try { return build(editor, rootDir, relPath, line); } catch (e) { return null; } // a lone surrogate makes encodeURIComponent throw
  }
  return { editorUrl: editorUrl, editors: EDITORS.slice(), validRoot: validRoot };
});
/* editor-links:end */
