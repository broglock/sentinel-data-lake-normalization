# Lab test plan: open questions

Run these in a lab tenant with the data lake onboarded (for example the Sentinel test workspace) before any customer claim. Record the result and date next to each test.

| # | Question | Test | Pass means |
|---|---|---|---|
| 2 | Do query-scoped `let` functions run in lake KQL? | Lake KQL query: `let f = (x:string) { strcat(x, "!") }; print r = f("ok")`. Repeat inside a one-time KQL job. | Returns `ok!` in both. Inlined parsers can use local helpers. |
| 3 | Do ASIM parsers run in advanced hunting against lake-only tables? | Move a test table to lake-only (for example a copy of Syslog in a `_CL` table), then in Defender advanced hunting run `_Im_Authentication(starttime=ago(1d))` and `imAuthentication` over a time range that only the lake holds. | Rows come back from the lake-only data. If yes, custom MCP tools saved from advanced hunting can call ASIM directly. |
| 4 | Can custom Sentinel MCP tools reach lake tables? | Save `HuntEntity_SPRK \| take 5` as a custom tool from advanced hunting and call it from an MCP client. | Rows return. If not, register the tools in your own data lake MCP. |
| 5 | Does `search_tables` find custom index tables? | Call `search_tables` with `hunt entity index` and with `HuntEntity`. | `HuntEntity_SPRK` is returned with its schema. If not, the agent instructions must name the tables. |
| 10 | Do DCR transforms apply to lake-only tables, and can split output carry new columns? | On a lake-only custom table, add a transformation that `extend`s `SrcIpAddr`; separately create a split rule on an analytics table and check the `_SPLT` table schema. | New column is populated in lake-only rows. |
| 11 | Can native ASim tables be set to the lake tier? | In Defender portal table management, try to switch `ASimNetworkSessionLogs` to data lake tier. | Tier change is accepted. |
| 13 | Is the parser YAML structure as assumed? | Open three parsers under `Parsers/ASimNetworkSession/Parsers/` in the Azure-Sentinel repo and check for `ParserQuery` and `ParserParams`, then run `generator/asim_expand.py` on each. | Keys exist; the report lists the helpers each parser calls. |
| new | Do `table()`, `join` and `where * has` run in lake KQL? | `table("Syslog") \| where TimeGenerated > ago(1h) \| where * has "sshd" \| take 5`; a `join` between two lake tables. | All three run. If `table()` fails, generate one pivot tool per high-volume table. |
| new | KQL job concurrency: 3 or 5? | Schedule 6 one-time jobs for the same minute. | Count how many run and how many are rejected; set the generator's stagger to match. |
| new | Notebook `save_as_table` options | Call `save_as_table(df, "Test_SPRK", write_options={"mode": "append"})` twice. | Second call appends. Adjust notebooks if the option name differs. |
| new | KQL and Spark record keys match | For one Syslog row, compute `record_key` in lake KQL and `spark_record_key` in a notebook. | Identical hex strings. If not, adjust the time format in the registry. |

Questions 1, 6, 7, 8, 9, 12 and 16 are answered by current Microsoft documentation (see the solution document, section 2). Questions 11 and 18 also go to the Sentinel product group.
