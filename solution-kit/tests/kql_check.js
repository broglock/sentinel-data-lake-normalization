// Parse and semantically check KQL files with Microsoft's Kusto.Language library.
// Setup once: npm install @kusto/language-service-next   (in this tests folder)
// Usage: node kql_check.js file1.kql [file2.kql ...]
// Table schemas below are minimal stand-ins; replace them with your real table schemas.
const fs = require("fs");
const path = require("path");
const base = path.join(__dirname, "node_modules/@kusto/language-service-next");
global.Bridge = undefined;
eval(fs.readFileSync(path.join(base, "bridge.js"), "utf8"));
eval(fs.readFileSync(path.join(base, "Kusto.Language.Bridge.js"), "utf8"));
const K = Kusto.Language;
const S = K.Symbols;

const tables = {
  Syslog: "(TimeGenerated:datetime, Computer:string, HostIP:string, ProcessName:string, ProcessID:int, Facility:string, SeverityLevel:string, SyslogMessage:string)",
  CommonSecurityLog: "(TimeGenerated:datetime, DeviceVendor:string, DeviceProduct:string, DeviceName:string, ReceiptTime:string, SourceIP:string, DestinationIP:string, SourcePort:int, DestinationPort:int, SourceUserName:string, DestinationUserName:string, RequestURL:string, DeviceAction:string, Protocol:string, DeviceCustomString2:string, DeviceCustomString2Label:string, AdditionalExtensions:string)",
  AppAudit_CL: "(TimeGenerated:datetime, Properties:dynamic)",
  Appliance_CL: "(TimeGenerated:datetime, RawData:string)",
  VpnAppliance_CL: "(TimeGenerated:datetime, RawData:string)",
  SecurityEvent: "(TimeGenerated:datetime, Computer:string, EventID:int, TargetUserName:string, TargetDomainName:string, IpAddress:string, WorkstationName:string, SubStatus:string, LogonType:int)",
  HuntEntity_SPRK: "(TimeGenerated:datetime, EventStartTime:datetime, SourceTable:string, SourceGroup:string, SourceRecordKey:string, EventVendor:string, EventProduct:string, EventSchema:string, EventType:string, EventResult:string, EntityType:string, Role:string, Value:string, ValueNorm:string, ValueType:string, MappingLayer:string, MappingTier:int)",
  HuntEvent_SPRK: "(TimeGenerated:datetime, EventStartTime:datetime, SourceTable:string, SourceGroup:string, SourceRecordKey:string, EventSchema:string, EventType:string, EventResult:string, SrcIpAddr:string, DstIpAddr:string, DstPortNumber:int, DvcAction:string, ActorUsername:string, TargetUsername:string, DvcHostname:string, MappingTier:int)",
  HuntCoverage_SPRK: "(TimeGenerated:datetime, SourceGroup:string, SourceTable:string, Tier:int, RawRows:long, IndexedRows:long, ExtractionRate:real, TemplateMatchRate:real, UnknownRoleShare:real, LastIndexed:datetime, Status:string)",
};
const syms = Object.entries(tables).map(([n, s]) => S.TableSymbol.From(s).WithName(n));
let db;
try { db = new S.DatabaseSymbol.$ctor1("db", syms); } catch (e) { db = new S.DatabaseSymbol.ctor("db", syms); }
const globals = K.GlobalState.Default.WithDatabase(db);

let bad = 0;
for (const f of process.argv.slice(2)) {
  let text = fs.readFileSync(f, "utf8");
  // MCP tool parameters look like {Name}; substitute sample values for checking
  text = text.replace(/\{LookbackDays\}/g, "7").replace(/\{LookbackHours\}/g, "24").replace(/\{[A-Za-z]+\}/g, "x");
  const code = K.KustoCode.ParseAndAnalyze(text, globals);
  const diags = code.GetDiagnostics();
  const list = [];
  for (let i = 0; i < diags.Count; i++) list.push(diags.getItem(i));
  const errs = list.filter(d => d.Severity === "Error");
  if (errs.length) {
    bad++;
    console.log(`FAIL ${path.basename(f)}`);
    for (const d of errs) {
      const line = text.slice(0, d.Start).split("\n").length;
      console.log(`  line ${line}: ${d.Message} :: ${JSON.stringify(text.substr(d.Start, Math.max(d.Length, 20)))}`);
    }
  } else console.log(`ok   ${path.basename(f)}`);
}
process.exit(bad ? 1 : 0);
