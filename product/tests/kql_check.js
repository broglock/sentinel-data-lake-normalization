// Parse and semantically check KQL files with Microsoft's Kusto.Language library.
// Setup once (in this folder): npm install @kusto/language-service-next
// Usage: node kql_check.js --schemas schemas.json file1.kql [file2.kql ...]
// schemas.json: {"TableName": "(Col:type, ...)", ...}
const fs = require("fs");
const path = require("path");
const base = path.join(process.env.KUSTO_LIB || path.join(__dirname, "node_modules"), "@kusto/language-service-next");
global.Bridge = undefined;
eval(fs.readFileSync(path.join(base, "bridge.js"), "utf8"));
eval(fs.readFileSync(path.join(base, "Kusto.Language.Bridge.js"), "utf8"));
const K = Kusto.Language;
const S = K.Symbols;
const args = process.argv.slice(2);
const si = args.indexOf("--schemas");
const tables = JSON.parse(fs.readFileSync(args[si + 1], "utf8"));
const files = args.filter((_, i) => i !== si && i !== si + 1);
const syms = Object.entries(tables).map(([n, s]) => S.TableSymbol.From(s).WithName(n));
let db;
try { db = new S.DatabaseSymbol.$ctor1("db", syms); } catch (e) { db = new S.DatabaseSymbol.ctor("db", syms); }
const globals = K.GlobalState.Default.WithDatabase(db);
let bad = 0;
for (const f of files) {
  let text = fs.readFileSync(f, "utf8");
  text = text.replace(/\{LookbackDays\}/g, "7").replace(/\{LookbackHours\}/g, "24").replace(/\{[A-Za-z]+\}/g, "x");
  const code = K.KustoCode.ParseAndAnalyze(text, globals);
  const diags = code.GetDiagnostics();
  const errs = [];
  for (let i = 0; i < diags.Count; i++) { const d = diags.getItem(i); if (d.Severity === "Error") errs.push(d); }
  if (errs.length) {
    bad++;
    console.log(`FAIL ${path.basename(f)}`);
    for (const d of errs) console.log(`  line ${text.slice(0, d.Start).split("\n").length}: ${d.Message} :: ${JSON.stringify(text.substr(d.Start, Math.max(d.Length, 20)))}`);
  } else console.log(`ok   ${path.basename(f)}`);
}
process.exit(bad ? 1 : 0);
