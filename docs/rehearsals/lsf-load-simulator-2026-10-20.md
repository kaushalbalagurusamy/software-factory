# Offline load-simulator tab

The dashboard now includes a system-design graph with an active-user slider,
per-user request rate, burst multiplier, declared service capacities and simulated
outages. All calculations run in the browser. No modeled service receives traffic.

[Normal load](screenshots/lsf-load-simulator.png)

[50,000-user overload scenario](screenshots/lsf-load-simulator-overload.png)

These screenshots use the explicitly labelled illustrative architecture. It is
not python-dotenv's architecture. Actual repos supply `docs/load-model.json`;
the LSF skill now instructs exploration to declare appropriate service topology
and source each capacity assumption. The model is also editable in the browser.
See `skills/lsf/LOAD-SIMULATOR.md` for equations, schema and limitations.

Independent browser interaction check: initial 200 req/s, slider to 50,000 users
producing 10,000 req/s and red overloaded components, and an outage checkbox
producing UNAVAILABLE all passed. This exercised actual headless Chrome DOM
controls. Node calculations cover converging paths, cache miss factors, bottleneck
ceiling, outage propagation, zero load, invalid rates/topology and cycles.

Local checks: the original LSF suite passed 90 checks before the final collector
case was added; the updated simulator/dashboard subset passed 11 checks. Native
HITL/lifecycle checks passed 268. VPS environment correction and final results
are recorded in the session handoff/status, not assumed from local results.

New VPS fallback projects may use the tested personal extension while the
coordinator base remains 30ed8d5. Existing pinned agents retain their runtimes.

Final VPS verification: all **91 LSF checks passed in 35.33 seconds** after
correcting noninteractive PATH to include the installed Claude binary. The
combined LSF/lifecycle VPS run exceeded its 180-second guard and is not counted
as a pass. Local lifecycle verification remains 268 passing checks.

Installed on both machines. An isolated VPS dashboard using the new runtime is
available through http://127.0.0.1:8893/#load; the served HTML and model collector
were checked. New fallback projects select personal runtime 1293faf while the
coordinator base is unchanged. Existing pinned projects were not restarted.
