**Source visual truth**

- `/var/folders/zm/1n48rm8n34b767q9b7k_46sm0000gn/T/codex-clipboard-58696a15-52b0-4a06-bdd0-516e88e5f7da.png`
- Source pixels: 298 × 1746. It is the rejected production state: a narrow terminal action column repeats `终止` and exposes clipped ellipses.

**Implementation evidence**

- `/Users/lianhaocheng/Documents/Codex/2026-08-11/new-chat/ssslab-proxy/qa/device-target-trace-production-final.png`
- `/Users/lianhaocheng/Documents/Codex/2026-08-11/new-chat/ssslab-proxy/qa/connections-production-right-columns.png`
- Combined comparison: `/Users/lianhaocheng/Documents/Codex/2026-08-11/new-chat/ssslab-proxy/qa/connection-tracing-design-qa-comparison-final.png`
- Browser viewport: 1512 × 1074 CSS px; production dark theme; browser screenshot output: 1512 × 1074 px.
- Comparison normalization: the 298 × 1746 source crop and 1512 × 1074 implementation capture were independently scaled to 900 px height and placed in one comparison image. The source is a focused before-state crop rather than a full screen, so exact frame proportions are intentionally not compared.
- State: 实时连接 → row detail → ssslab-login-1 device history → 实时 target trace.

**Findings**

- No actionable P0/P1/P2 issue remains.
- The repeated row action column and clipped ellipsis shown in the source are absent. Destructive actions are moved to a contextual right-click menu, and the reclaimed column displays cumulative per-connection traffic.
- The device drill-down now provides a scrollable host-level trace with separate upload, download, and cumulative bytes. This directly supports the device → destination → traffic task that was missing from the source state.
- Full HTTPS URL paths remain outside this screen's claim because mihomo does not expose encrypted paths without MITM; the UI accurately labels the observable unit as `目标主机`.

**Required fidelity surfaces**

- Fonts and typography: existing Inter / Noto Sans SC stack, 11–15 px operational text, numeric emphasis, and truncation behavior are preserved. The new context actions and trace columns use the same optical hierarchy as the existing console.
- Spacing and layout rhythm: the table remains dense and independently scrollable. The detail drawer, context menu, and request-trace table reuse existing 7–11 px radii, borders, compact rows, and panel rhythm.
- Colors and visual tokens: existing dark surface, border, primary blue, semantic red, and muted text tokens are reused; no new competing palette was introduced.
- Image and asset quality: this workflow contains no raster product assets. All visible action icons use the existing Phosphor icon library; no handcrafted SVG, CSS illustration, emoji, or placeholder asset was introduced.
- Copy and content: `操作`/repeated `终止` is removed from the table. Action wording is explicit in the right-click menu, and the target trace uses `目标主机`, `上传`, `下载`, and `累计` without redundant microcopy.

**Interactions tested**

- Right-clicking a production connection opens `连接详情`, `设备流量历史`, `为目标增加规则`, and `终止连接`.
- Left-clicking a connection opens a drawer with source device, target host/IP and port, protocol, duration, cumulative up/down bytes, rates, matched rule, and complete strategy chain.
- The quick-rule editor loads the real policy inventory and previews an exact `DOMAIN`, `DOMAIN-SUFFIX`, or `IP-CIDR` mihomo rule. The destructive save/apply action was not submitted during QA.
- Device history returns seven real targets for the tested device and renders accumulated upload/download/total bytes.
- Browser console: no errors during production load and the tested interaction path.
- Production health: Web service healthy and mihomo reachable.

**Comparison history**

- Pass 1: device drill-down always highlighted `流量分析`, even when entered from `实时连接`. Fixed by preserving the originating navigation section while the device analysis is open.
- Pass 2: production evidence shows `实时连接` remains selected, host-level traffic values populate from persisted/live data, and no P0/P1/P2 visual or interaction regression remains.

**Follow-up polish**

- P3: a future opt-in MITM subsystem could add URL-path auditing for explicitly enrolled devices, but it should remain separate from normal gateway metadata because it changes certificate trust and privacy boundaries.

final result: passed
