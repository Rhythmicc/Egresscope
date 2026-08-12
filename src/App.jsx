import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  ArrowsDownUp,
  CaretDown,
  ChartDonut,
  CheckCircle,
  CirclesFour,
  ClockCounterClockwise,
  CloudArrowDown,
  Copy,
  Cpu,
  DotsThreeVertical,
  Desktop,
  DownloadSimple,
  FileCode,
  Funnel,
  Gauge,
  Gear,
  GlobeHemisphereEast,
  Globe,
  GoogleLogo,
  GithubLogo,
  HardDrives,
  ListMagnifyingGlass,
  LinkSimple,
  Lightning,
  MagnifyingGlass,
  Moon,
  OpenAiLogo,
  Pause,
  PencilSimple,
  PlugsConnected,
  Plus,
  Power,
  Pulse,
  Rows,
  ShieldCheck,
  SignOut,
  SlidersHorizontal,
  Stack,
  Sun,
  TelegramLogo,
  Trash,
  Users,
  WarningCircle,
  WifiHigh,
  WindowsLogo,
  YoutubeLogo,
  X,
  XLogo,
  AppleLogo,
} from "@phosphor-icons/react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Sankey,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, subscribeLive } from "./api";
import { demoDashboard, demoDevice, demoStrategies } from "./demo-data";

const DEMO_MODE = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === "true";

const NAV = [
  { id: "dashboard", label: "状态概览", icon: Gauge, viewer: true },
  { id: "connections", label: "实时连接", icon: PlugsConnected, viewer: true },
  { id: "audit", label: "流量分析", icon: ListMagnifyingGlass, viewer: true },
  { id: "strategies", label: "分流策略", icon: ArrowsDownUp },
  { id: "rules", label: "规则管理", icon: SlidersHorizontal },
  { id: "subscriptions", label: "订阅管理", icon: CloudArrowDown, viewer: true },
  { id: "gateway", label: "网关设置", icon: WifiHigh },
  { id: "system", label: "用户管理", icon: Gear },
];

const PAGE_TITLES = {
  dashboard: ["状态概览", "整个局域网的实时运行概览"],
  connections: ["实时连接", "查看当前活跃会话及完整转发链路"],
  audit: ["流量分析", "按服务、目标地址和来源设备回溯流量"],
  strategies: ["分流策略", "常用策略优先，配置顺序保持可追溯"],
  rules: ["规则管理", "规则集、请求匹配与节点来源相互独立"],
  subscriptions: ["订阅管理", "订阅管理是网关能力的一部分，而不是首页"],
  gateway: ["网关设置", "核心状态、配置与故障转移"],
  system: ["用户管理", "用户隔离、设备别名与审计保留策略"],
};

const canOpenPage = (page, user) => user?.role === "admin" || Boolean(NAV.find(item => item.id === page)?.viewer);

const bytes = (value = 0) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = Number(value) || 0;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`;
};

const rate = (value = 0) => `${bytes(value)}/s`;
const bucketDuration = (seconds = 0) => seconds >= 86400 ? `${seconds / 86400} 天` : seconds >= 3600 ? `${seconds / 3600} 小时` : seconds >= 60 ? `${seconds / 60} 分钟` : `${seconds} 秒`;

function StatusPill({ online }) {
  return (
    <div className={`status-pill ${online ? "is-online" : "is-offline"}`}>
      <span className="status-dot" />
      {online ? "网关运行正常" : "网关连接中断"}
    </div>
  );
}

function Sidebar({ page, setPage, collapsed, setCollapsed, user }) {
  return (
    <aside className={`sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <button className="brand" onClick={() => setPage("dashboard")} aria-label="返回状态概览">
        <span className="brand-mark"><Stack weight="fill" /></span>
        {!collapsed && <span>Egresscope</span>}
      </button>
      <nav className="nav-list" aria-label="主导航">
        {NAV.filter(item => user?.role === "admin" || item.viewer).map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => setPage(item.id)}
              title={item.label}
            >
              <Icon weight={page === item.id ? "fill" : "regular"} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>
      <button className="collapse-button" onClick={() => setCollapsed(!collapsed)}>
        <Rows /> {!collapsed && <span>收起侧栏</span>}
      </button>
    </aside>
  );
}

function Topbar({ title, subtitle, online, theme, cycleTheme, onLogout, user }) {
  return (
    <header className="topbar">
      <div className="page-title">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="topbar-actions">
        <StatusPill online={online} />
        <span className="last-refresh">刚刚刷新</span>
        <button className="icon-button theme-button" onClick={cycleTheme} title={`当前：${theme}`}>
          {theme === "dark" ? <Moon weight="fill" /> : theme === "light" ? <Sun weight="fill" /> : <Desktop />}
        </button>
        <div className="profile-identity" aria-label={`当前用户：${user?.username || "demo"}`}><span className="avatar">{(user?.username || "demo").slice(0, 1).toUpperCase()}</span><span>{user?.username || "demo"}</span></div>
        <button className="icon-button" onClick={onLogout} title="退出登录"><SignOut /></button>
      </div>
    </header>
  );
}

function StatCard({ icon: Icon, label, value, tone }) {
  return (
    <article className="stat-card">
      <span className={`stat-icon ${tone}`}><Icon weight="fill" /></span>
      <div className="stat-card-copy">
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function TrafficTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => <span key={item.dataKey} style={{ color: item.color }}>{item.name} {bytes(item.value)}</span>)}
    </div>
  );
}

function TrafficChart({ data, compact = false }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 12, right: 12, left: compact ? -20 : 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={11} minTickGap={30} />
        <YAxis tickFormatter={(v) => bytes(v)} tickLine={false} axisLine={false} fontSize={11} width={compact ? 48 : 62} />
        <Tooltip content={<TrafficTooltip />} />
        <Area name="下载" dataKey="down" type="monotone" stroke="#4177ef" fill="#4177ef" fillOpacity={0.13} strokeWidth={2} isAnimationActive={false} />
        <Area name="上传" dataKey="up" type="monotone" stroke="#20a777" fill="#20a777" fillOpacity={0.1} strokeWidth={2} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const DASHBOARD_RANGES = [
  ["live", "实时"],
  ["1h", "1 小时"],
  ["6h", "6 小时"],
  ["24h", "24 小时"],
  ["7d", "7 天"],
  ["14d", "14 天"],
  ["month", "本月"],
];

function DashboardFilters({ range, setRange, loading }) {
  return (
    <div className="filters">
      <div className="segmented">
        {DASHBOARD_RANGES.map(([key, label]) => <button key={key} disabled={loading} className={range === key ? "active" : ""} onClick={() => setRange(key)}>{label}</button>)}
      </div>
      <button className="filter-button"><Funnel /> 全部设备 <CaretDown /></button>
      <button className="filter-button"><GlobeHemisphereEast /> 全部链路 <CaretDown /></button>
    </div>
  );
}

function DeviceRanking({ devices, onSelect }) {
  const max = Math.max(...devices.map((d) => d.total), 1);
  return (
    <section className="panel device-ranking">
      <div className="panel-heading"><h2>设备流量排行</h2><button className="text-button">查看全部</button></div>
      <div className="ranking-list">
        {devices.slice(0, 5).map((device, index) => (
          <button key={device.ip} className="ranking-row" onClick={() => onSelect(device)}>
            <span className="rank">{index + 1}</span>
            <span className="device-avatar"><HardDrives /></span>
            <span className="device-copy"><strong>{device.name}</strong><small>{device.ip}</small><i style={{ width: `${Math.max(8, device.total / max * 100)}%` }} /></span>
            <span className="device-rate"><strong>{rate(device.down)}</strong><small>↓ {bytes(device.total)}</small></span>
          </button>
        ))}
      </div>
    </section>
  );
}

function ChainUsage({ chains }) {
  const colors = ["#4777ef", "#22a778", "#8458d9", "#e79b37", "#e05265"];
  return (
    <section className="panel chain-usage">
      <div className="panel-heading"><h2>出口模式分布</h2><ChartDonut /></div>
      <div className="donut-wrap">
        <div className="donut-chart">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart><Pie data={chains} dataKey="value" nameKey="name" innerRadius={50} outerRadius={70} paddingAngle={3} stroke="none">{chains.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}</Pie><Tooltip formatter={(v) => bytes(v)} /></PieChart>
          </ResponsiveContainer>
          <div className="donut-center"><strong>{bytes(chains.reduce((sum, c) => sum + c.value, 0))}</strong><span>合计</span></div>
        </div>
        <div className="legend-list">{chains.map((chain, i) => <div key={chain.name}><span className="legend-dot" style={{ background: colors[i % colors.length] }} /><strong>{chain.name}</strong><small>{chain.percent}%</small></div>)}</div>
      </div>
    </section>
  );
}

const connectionProtocol = (connection) => {
  const network = String(connection.network || "tcp").toUpperCase();
  if (network === "UDP" && Number(connection.destinationPort) === 443) return "QUIC";
  if (network === "TCP" && Number(connection.destinationPort) === 443) return "HTTPS";
  return network;
};

function ConnectionTable({ connections, onDevice, onSelect, onContext, dense = false, operational = false }) {
  return (
    <div className={`connection-table-wrap ${dense ? "dense" : ""} ${operational ? "operational" : ""}`} data-testid={operational ? "connections-scroll" : undefined}>
      <table className="connection-table">
        <thead><tr><th>设备</th><th>目标</th><th>协议</th><th>命中规则</th><th>策略链路</th><th className="numeric">上行速率</th><th className="numeric">下行速率</th><th className="numeric">累计流量</th><th>持续时间</th></tr></thead>
        <tbody>
          {connections.map((connection) => { const protocol = connectionProtocol(connection); const moving = connection.upRate + connection.downRate > 0; return (
            <tr key={connection.id} className={moving ? "is-moving" : "is-idle"} onClick={() => onSelect ? onSelect(connection) : onDevice?.({ name: connection.device, ip: connection.sourceIP })} onContextMenu={(event) => { if (!onContext) return; event.preventDefault(); onContext(event, connection); }}>
              <td><span className="connection-device"><i /> <span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></span></td>
              <td><strong>{connection.host || connection.destinationIP}</strong><small>{connection.destinationIP}:{connection.destinationPort}</small></td>
              <td><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></td>
              <td>{connection.rule}</td>
              <td><div className="chain-text">{connection.chain.map((item, i) => <span key={`${item}-${i}`}>{item}</span>)}</div></td>
              <td className="numeric up">{rate(connection.upRate)}</td>
              <td className="numeric down">{rate(connection.downRate)}</td>
              <td className="numeric cumulative">{bytes((connection.upload || 0) + (connection.download || 0))}</td>
              <td>{connection.duration}</td>
            </tr>
          ); })}
        </tbody>
      </table>
    </div>
  );
}

function ConnectionContextMenu({ state, canManage, onClose, onInspect, onDevice, onTerminate, onAddRule }) {
  if (!state) return null;
  const connection = state.connection;
  return <div className="connection-context-menu" style={{ left: state.x, top: state.y }} onClick={event => event.stopPropagation()} onContextMenu={event => event.preventDefault()}>
    <div className="context-target"><strong>{connection.host || connection.destinationIP}</strong><span>{connection.device} · {bytes((connection.upload || 0) + (connection.download || 0))}</span></div>
    <button onClick={() => { onInspect(connection); onClose(); }}><ListMagnifyingGlass />连接详情</button>
    <button onClick={() => { onDevice({ name: connection.device, ip: connection.sourceIP }); onClose(); }}><Desktop />设备流量历史</button>
    {canManage && <><div className="context-divider"/><button onClick={() => { onAddRule(connection); onClose(); }}><Plus />为目标增加规则</button><button className="danger" onClick={() => { onTerminate(connection.id); onClose(); }}><Power />终止连接</button></>}
  </div>;
}

function ConnectionInspector({ connection, onClose, onDevice }) {
  if (!connection) return null;
  const protocol = connectionProtocol(connection);
  const total = (connection.upload || 0) + (connection.download || 0);
  return <div className="connection-inspector-layer" onMouseDown={onClose}>
    <aside className="connection-inspector" onMouseDown={event => event.stopPropagation()}>
      <div className="inspector-heading"><div><span>连接详情</span><h2>{connection.host || connection.destinationIP}</h2></div><button onClick={onClose}><X /></button></div>
      <div className="inspector-summary"><div><span>累计流量</span><strong>{bytes(total)}</strong></div><div><span>当前速率</span><strong>{rate((connection.upRate || 0) + (connection.downRate || 0))}</strong></div></div>
      <dl className="connection-facts">
        <div><dt>来源设备</dt><dd>{connection.device}<small>{connection.sourceIP}</small></dd></div>
        <div><dt>目标地址</dt><dd>{connection.host || "IP 连接"}<small>{connection.destinationIP}:{connection.destinationPort}</small></dd></div>
        <div><dt>协议</dt><dd><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></dd></div>
        <div><dt>持续时间</dt><dd>{connection.duration}</dd></div>
        <div><dt>上传</dt><dd>{bytes(connection.upload)}<small>{rate(connection.upRate)}</small></dd></div>
        <div><dt>下载</dt><dd>{bytes(connection.download)}<small>{rate(connection.downRate)}</small></dd></div>
        <div className="wide"><dt>命中规则</dt><dd>{connection.rule}</dd></div>
        <div className="wide"><dt>完整策略链路</dt><dd><div className="inspector-chain">{connection.chain.map((item,index)=><span key={`${item}-${index}`}>{item}</span>)}</div></dd></div>
      </dl>
      <button className="primary-button inspector-device-button" onClick={() => onDevice({ name: connection.device, ip: connection.sourceIP })}>查看该设备的目标与历史流量</button>
    </aside>
  </div>;
}

function QuickRuleModal({ editor, setEditor, onSave }) {
  if (!editor) return null;
  const prefix = editor.matchType === "IP-CIDR" ? `${editor.value}${editor.value.includes(":") ? "/128" : "/32"}` : editor.value;
  const content = `${editor.matchType},${prefix},${editor.policy}${editor.matchType === "IP-CIDR" ? ",no-resolve" : ""}`;
  return <div className="modal-backdrop" onMouseDown={() => !editor.busy && setEditor(null)}><form className="user-modal quick-rule-modal" onMouseDown={event => event.stopPropagation()} onSubmit={event => { event.preventDefault(); onSave({ ...editor, content }); }}>
    <div className="modal-heading"><div><span className="eyebrow">实时连接</span><h3>为目标增加规则</h3></div><button type="button" disabled={editor.busy} onClick={() => setEditor(null)}><X /></button></div>
    <div className="quick-rule-grid"><label>匹配方式<select value={editor.matchType} onChange={event => setEditor({ ...editor, matchType: event.target.value })}><option value="DOMAIN">精确域名</option><option value="DOMAIN-SUFFIX">域名后缀</option><option value="IP-CIDR">目标 IP</option></select></label><label>目标<input required value={editor.value} onChange={event => setEditor({ ...editor, value: event.target.value })}/></label></div>
    <label>执行策略<select value={editor.policy} onChange={event => setEditor({ ...editor, policy: event.target.value })}>{editor.policies.map(policy => <option key={policy}>{policy}</option>)}</select></label>
    <div className="rule-preview"><span>将写入</span><code>{content}</code></div>
    {editor.error && <div className="login-error"><WarningCircle />{editor.error}</div>}
    <button className="primary-button modal-submit" disabled={editor.busy || !editor.policy}>{editor.busy ? "正在应用…" : "保存并应用"}</button>
  </form></div>;
}

function StrategySummary({ strategies, onOpen }) {
  return (
    <section className="panel strategy-summary">
      <div className="panel-heading"><h2>常用策略</h2><button className="text-button" onClick={onOpen}>管理策略</button></div>
      <div className="strategy-list">
        {strategies.primary.slice(0, 5).map((group, index) => (
          <div className="strategy-row" key={group.name}>
            <span className="strategy-index">{index + 1}</span>
            <div><strong>{group.name}</strong></div>
            <span className="strategy-now">{group.now}</span>
          </div>
        ))}
      </div>
      <button className="secondary-strategies">其他规则策略 <span>{strategies.secondaryCount}</span><CaretDown /></button>
    </section>
  );
}

function Dashboard({ data, strategies, onDevice, onNavigate, canManage }) {
  const [range, setRange] = useState("24h");
  const [rangeData, setRangeData] = useState(null);
  const [rangeLoading, setRangeLoading] = useState(false);
  useEffect(() => {
    let active = true;
    let timer;
    setRangeData(null);
    const loadRange = async () => {
      setRangeLoading(true);
      try { const result = await api.dashboard(range); if (active) setRangeData(result); }
      catch { /* Keep the last successful range while the next refresh retries. */ }
      finally { if (active) setRangeLoading(false); }
    };
    loadRange();
    timer = setInterval(loadRange, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [range]);
  const chartSource = rangeData || (data.timelineRange === range ? data : null);
  const chartTimeline = chartSource?.timeline || [];
  const rangeLabel = DASHBOARD_RANGES.find(([key]) => key === range)?.[1] || "实时";
  const rangeCopy = range === "month" ? "本月" : `最近 ${rangeLabel}`;
  const trafficSummary = chartSource?.timelineSummary || { up: 0, down: 0, traffic: 0 };
  const bucketCopy = bucketDuration(chartSource?.timelineBucketSeconds || 0);
  return (
    <div className="dashboard page-content">
      <div className="stats-grid">
        <StatCard icon={CheckCircle} label="网关状态" value={data.status.online ? "运行正常" : "连接中断"} tone="green" />
        <StatCard icon={Pulse} label="活跃连接" value={data.totals.active.toLocaleString()} tone="blue" />
        <StatCard icon={CloudArrowDown} label="实时带宽" value={`↓ ${rate(data.totals.downRate)}`} tone="violet" />
        <StatCard icon={ChartDonut} label="本月流量" value={bytes(data.totals.month ?? data.totals.today)} tone="orange" />
      </div>
      <section className="panel throughput-panel">
        <div className="panel-heading throughput-heading"><div><h2>流量趋势</h2><p>{rangeCopy} · 每 {bucketCopy} 实际消耗流量</p></div><DashboardFilters range={range} setRange={setRange} loading={rangeLoading} /></div>
        <div className="traffic-totals"><span className="traffic-total down"><i />下载<strong>{bytes(trafficSummary.down)}</strong></span><span className="traffic-total up"><i />上传<strong>{bytes(trafficSummary.up)}</strong></span><span className="traffic-total combined">合计<strong>{bytes(trafficSummary.traffic)}</strong></span>{rangeLoading && <small>正在加载…</small>}</div>
        <div className="throughput-chart"><TrafficChart data={chartTimeline} /></div>
      </section>
      <div className={`dashboard-columns ${canManage ? "" : "viewer-columns"}`}>
        <DeviceRanking devices={data.devices} onSelect={onDevice} />
        <ChainUsage chains={data.chains} />
        {canManage && <StrategySummary strategies={strategies} onOpen={() => onNavigate("strategies")} />}
      </div>
      <section className="panel live-panel">
        <div className="panel-heading"><h2>实时连接</h2><button className="text-button" onClick={() => onNavigate("connections")}>查看全部连接</button></div>
        <ConnectionTable connections={data.connections.slice(0, 6)} onDevice={onDevice} dense />
      </section>
    </div>
  );
}

function FlowNode({ x, y, width, height, index, payload, containerWidth }) {
  const source = x < containerWidth * 0.18;
  const sink = x > containerWidth * 0.72;
  const color = source ? "#6ee7b7" : sink ? "#60a5fa" : index % 2 ? "#c084fc" : "#38bdf8";
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={4} fill={color} fillOpacity={0.9} />
      <text x={source ? x + width + 8 : sink ? x - 8 : x + width / 2} y={y + height / 2} textAnchor={source ? "start" : sink ? "end" : "middle"} dominantBaseline="middle" fill="#dbeafe" fontSize="11" fontWeight="600">{payload.name}</text>
    </g>
  );
}

function DeviceFlow({ device, onBack }) {
  const [range, setRange] = useState("live");
  const [snapshot, setSnapshot] = useState(device);
  const [loading, setLoading] = useState(false);
  useEffect(() => { setSnapshot(device); setRange("live"); }, [device.ip]);
  useEffect(() => {
    let active = true;
    let timer;
    const load = async () => {
      setLoading(true);
      try { const result = await api.device(device.ip, range); if (active) setSnapshot(result); }
      catch { /* Keep the latest snapshot in the local prototype or during a retry. */ }
      finally { if (active) setLoading(false); }
    };
    load();
    timer = setInterval(load, range === "live" ? 3000 : 30000);
    return () => { active = false; clearInterval(timer); };
  }, [device.ip, range]);
  const current = snapshot || device;
  const flow = current.flow || { nodes: [], links: [] };
  const summary = current.rangeSummary || { up: 0, down: 0, traffic: 0 };
  const rangeLabel = DASHBOARD_RANGES.find(([key]) => key === range)?.[1] || "实时";
  const live = range === "live";
  const rangeCopy = live ? "最近 15 分钟" : range === "month" ? "本月" : `最近 ${rangeLabel}`;
  const bucketCopy = bucketDuration(current.timelineBucketSeconds || 0);
  return (
    <div className="device-analysis page-content dark-workspace">
      <div className="device-analysis-header">
        <button className="back-button" onClick={onBack}>← 返回概览</button>
        <div><h2>{current.name}</h2><p>{current.ip} · <span className="online-copy">{current.active ? "在线" : "最近使用"}</span></p></div>
        <div className="device-live-metrics"><span>{live ? "活跃连接" : "区间流量"}<strong>{live ? current.active || 0 : bytes(summary.traffic)}</strong></span><span>{live ? "实时上行" : "上传流量"}<strong>{live ? rate(current.up || 0) : bytes(summary.up)}</strong></span><span>{live ? "实时下行" : "下载流量"}<strong>{live ? rate(current.down || 0) : bytes(summary.down)}</strong></span></div>
      </div>
      <div className="flow-toolbar">
        <div className="segmented dark-segmented device-range-tabs">{DASHBOARD_RANGES.map(([key,label])=><button key={key} disabled={loading} className={range===key?"active":""} onClick={()=>setRange(key)}>{label}</button>)}</div>
        <button className="dark-filter"><Funnel /> 所有连接 <CaretDown /></button>
        <div className="live-indicator"><span /> {loading ? "加载中" : live ? "3 秒刷新" : rangeCopy}</div>
      </div>
      <section className="flow-panel">
        <div className="flow-panel-title"><h3>{rangeCopy}累计流量路径</h3><div className="flow-total">累计流量 <strong>{bytes(summary.traffic)}</strong></div></div>
        <div className="flow-column-labels"><span>来源设备</span><span>命中规则</span><span>策略组</span><span>出口节点</span></div>
        <div className="sankey-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <Sankey data={flow} node={<FlowNode />} nodePadding={28} nodeWidth={8} link={{ stroke: "#4f8df7", strokeOpacity: 0.22 }} margin={{ top: 12, right: 110, bottom: 12, left: 110 }}>
              <Tooltip formatter={(v) => bytes(v)} contentStyle={{ background: "#172033", border: "1px solid #2c3850", borderRadius: 8, color: "#eef4ff" }} />
            </Sankey>
          </ResponsiveContainer>
        </div>
      </section>
      <div className="analysis-bottom-grid">
        <section className="dark-panel device-traffic-panel">
          <div className="dark-panel-heading"><div><h3>设备流量趋势</h3><p>{rangeCopy} · 每 {bucketCopy} 实际消耗流量</p></div><Pulse /></div>
          <div className="device-chart"><TrafficChart data={current.timeline || []} compact /></div>
        </section>
        <section className="dark-panel destinations-panel">
          <div className="dark-panel-heading"><div><h3>请求目标与流量</h3></div><GlobeHemisphereEast /></div>
          <div className="destination-trace-head"><span>目标主机</span><span>上传</span><span>下载</span><span>累计</span></div>
          <div className="destination-trace-list">{(current.destinations || []).map((item) => <div className="destination-trace-row" key={item.host}><span><strong>{item.host}</strong><small>{item.rule || item.service}</small></span><b>{bytes(item.up || 0)}</b><b>{bytes(item.down || 0)}</b><b>{bytes(item.traffic ?? ((item.up || 0) + (item.down || 0)))}</b></div>)}</div>
        </section>
        <section className="dark-panel anomaly-panel">
          <div className="dark-panel-heading"><div><h3>审计提示</h3><p>{live ? "最近 24 小时" : rangeCopy}</p></div><ShieldCheck /></div>
          <div className="anomaly-item"><WarningCircle weight="fill" /><div><strong>发现 1 次链路切换</strong><p>美国最佳延迟升高，自动切至 us-lax-03。</p><small>18 分钟前</small></div></div>
          <div className="audit-ok"><CheckCircle weight="fill" /> 未发现异常目标或突发外联</div>
        </section>
      </div>
    </div>
  );
}

function ConnectionsPage({ data, onDevice, canManage }) {
  const [query, setQuery] = useState("");
  const [deviceFilter, setDeviceFilter] = useState("");
  const [networkFilter, setNetworkFilter] = useState("");
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState([]);
  const [compact, setCompact] = useState(true);
  const [message, setMessage] = useState("");
  const [contextMenu, setContextMenu] = useState(null);
  const [inspected, setInspected] = useState(null);
  const [quickRule, setQuickRule] = useState(null);
  const source = paused ? snapshot : data.connections;
  const devices = [...new Map(data.connections.map(connection => [connection.sourceIP, { ip: connection.sourceIP, name: connection.device }])).values()].sort((a,b) => a.name.localeCompare(b.name));
  const filtered = source.filter((c) => (!deviceFilter || c.sourceIP === deviceFilter) && (!networkFilter || connectionProtocol(c) === networkFilter) && `${c.device} ${c.sourceIP} ${c.host} ${c.destinationIP} ${c.rule} ${c.chain.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const togglePause = () => { if (!paused) setSnapshot(data.connections); setPaused(current => !current); };
  useEffect(() => {
    if (!contextMenu) return undefined;
    const close = () => setContextMenu(null);
    const escape = event => { if (event.key === "Escape") close(); };
    document.addEventListener("click", close);
    document.addEventListener("scroll", close, true);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("click", close); document.removeEventListener("scroll", close, true); document.removeEventListener("keydown", escape); };
  }, [contextMenu]);
  const openContextMenu = (event, connection) => setContextMenu({ connection, x: Math.max(8, Math.min(event.clientX, window.innerWidth - 246)), y: Math.max(8, Math.min(event.clientY, window.innerHeight - (canManage ? 244 : 164))) });
  const closeOne = async (id) => {
    try { await api.closeConnection(id); setMessage("连接已终止；列表将在下一次采样时更新。"); }
    catch (error) { setMessage(error.message); }
  };
  const openQuickRule = async (connection) => {
    const host = connection.host && !/^[\d.:]+$/.test(connection.host) ? connection.host : "";
    const initial = { connection, matchType: host ? "DOMAIN" : "IP-CIDR", value: host || connection.destinationIP, policy: "", policies: [], busy: true, error: "" };
    setQuickRule(initial);
    try {
      const workspace = await api.ruleWorkspace();
      const policies = [...new Set([...(workspace.availablePolicies || []), "DIRECT", "REJECT"])];
      const policy = connection.chain.find(item => policies.includes(item)) || policies.find(item => item === "节点选择") || policies[0] || "DIRECT";
      setQuickRule({ ...initial, policy, policies, busy: false });
    } catch (error) { setQuickRule({ ...initial, policies: ["DIRECT", "REJECT"], policy: "DIRECT", busy: false, error: error.message }); }
  };
  const saveQuickRule = async (editor) => {
    setQuickRule({ ...editor, busy: true, error: "" });
    try {
      await api.createCustomRule({ content: editor.content, placement: "before", note: `来自实时连接：${editor.connection.device}` });
      await api.applyRules();
      setMessage(`规则已应用：${editor.content}`);
      setQuickRule(null);
    } catch (error) { setQuickRule({ ...editor, busy: false, error: error.message }); }
  };
  const closeAll = async () => {
    if (!window.confirm("确定终止当前全部连接？应用可能会自动重连。")) return;
    try { await api.closeAllConnections(); setMessage("全部连接已终止。"); }
    catch (error) { setMessage(error.message); }
  };
  return (
    <div className="page-content list-page connections-page">
      <section className="panel full-height-panel connections-workspace">
        <div className="connection-modebar"><div><button className="active">活动连接</button><button onClick={() => setNetworkFilter("")}>全部协议</button></div></div>
        <div className="list-toolbar">
          <select value={deviceFilter} onChange={event => setDeviceFilter(event.target.value)}><option value="">所有设备</option>{devices.map(device => <option key={device.ip} value={device.ip}>{device.name} · {device.ip}</option>)}</select>
          <select value={networkFilter} onChange={event => setNetworkFilter(event.target.value)}><option value="">所有协议</option><option value="HTTPS">HTTPS</option><option value="QUIC">QUIC</option><option value="TCP">TCP</option><option value="UDP">UDP</option></select>
          <div className="search-box"><MagnifyingGlass /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索设备、目标、规则或策略链路" />{query && <button onClick={() => setQuery("")}><X /></button>}</div>
          <button className={`toolbar-icon ${paused ? "active" : ""}`} title={paused ? "恢复自动刷新" : "暂停列表"} onClick={togglePause}>{paused ? <Pulse weight="fill" /> : <Pause weight="fill" />}</button>
          <button className="toolbar-icon" title={compact ? "切换舒适密度" : "切换紧凑密度"} onClick={() => setCompact(current => !current)}>{compact ? <Rows /> : <CirclesFour />}</button>
          {canManage && <button className="danger-button" onClick={closeAll}>终止全部</button>}
        </div>
        {message && <div className="inline-message">{message}</div>}
        <ConnectionTable connections={filtered} onSelect={setInspected} onContext={openContextMenu} dense={compact} operational />
        <div className="list-summary"><span className={paused ? "paused-dot" : "live-dot"} />{paused ? "已暂停" : "实时"}<b>{filtered.length} 条连接</b><span>↑ {rate(data.totals.upRate)}</span><span>↓ {rate(data.totals.downRate)}</span></div>
      </section>
      <ConnectionContextMenu state={contextMenu} canManage={canManage} onClose={() => setContextMenu(null)} onInspect={setInspected} onDevice={onDevice} onTerminate={closeOne} onAddRule={openQuickRule} />
      <ConnectionInspector connection={inspected} onClose={() => setInspected(null)} onDevice={device => { setInspected(null); onDevice(device); }} />
      <QuickRuleModal editor={quickRule} setEditor={setQuickRule} onSave={saveQuickRule} />
    </div>
  );
}

const ANALYSIS_DEMO = {
  totals: { up: 2060000000, down: 4350000000, traffic: 6410000000, connections: 1804, proxyUp: 1530000000, proxyDown: 2850000000, proxy: 4380000000, directUp: 530000000, directDown: 1500000000, direct: 2030000000 },
  items: [
    { id: "OpenAI", name: "OpenAI", icon: "openai", up: 8300000, down: 42000000, traffic: 50300000, connections: 82, percent: 39.9, details: [{ host: "chatgpt.com", up: 1400000, down: 37700000, connections: 73 }, { host: "openai.com", up: 6100000, down: 2100000, connections: 4 }, { host: "browser-intake-datadoghq.com", up: 400000, down: 1200000, connections: 4 }, { host: "oaistatic.com", up: 400000, down: 1000000, connections: 1 }] },
    { id: "Direct IP", name: "Direct IP", icon: "direct", up: 18500000, down: 23200000, traffic: 41700000, connections: 6, percent: 33.1, details: [] },
    { id: "Telegram", name: "Telegram", icon: "telegram", up: 600000, down: 11000000, traffic: 11600000, connections: 40, percent: 9.2, details: [] },
    { id: "X", name: "X (Twitter)", icon: "x", up: 200000, down: 8200000, traffic: 8400000, connections: 13, percent: 6.7, details: [] },
    { id: "GitHub", name: "GitHub", icon: "github", up: 100000, down: 6400000, traffic: 6500000, connections: 23, percent: 5.2, details: [] },
    { id: "Microsoft", name: "Microsoft", icon: "microsoft", up: 2700000, down: 2000000, traffic: 4700000, connections: 28, percent: 3.7, details: [] },
    { id: "Apple", name: "Apple", icon: "apple", up: 800000, down: 1900000, traffic: 2700000, connections: 31, percent: 2.2, details: [] },
  ],
  attribution: {
    service: "OpenAI",
    period: "day",
    devices: [
      { ip: "192.168.31.225", name: "ssslab-login-1", traffic: 1290000000, percent: 41.6 },
      { ip: "192.168.31.42", name: "U55C", traffic: 1000000000, percent: 32.2 },
      { ip: "192.168.31.177", name: "192.168.31.177", traffic: 573700000, percent: 18.5 },
      { ip: "10.18.18.2", name: "9462", traffic: 194700000, percent: 6.3 },
    ],
    buckets: [
      ["08-06",180,140,80,20],["08-07",175,125,75,27],["08-08",210,130,80,26],
      ["08-09",190,120,85,25],["08-10",202,126,88,24],["08-11",185,125,82,25],["08-12",180,120,75,26],
    ].map(([time,a,b,c,d]) => ({ time, values: { "192.168.31.225": a*1024**2, "192.168.31.42": b*1024**2, "192.168.31.177": c*1024**2, "10.18.18.2": d*1024**2 } })),
  },
};

const DEMO_USAGE_HISTORY = {
  currentMonth: 2.84 * 1024 ** 4, previousMonth: 2.55 * 1024 ** 4, currentYear: 18.7 * 1024 ** 4, previousYear: 41.2 * 1024 ** 4, recordedTotal: 59.9 * 1024 ** 4,
  months: [["2026-08",2.84],["2026-07",2.55],["2026-06",3.18],["2026-05",2.72],["2026-04",3.43],["2026-03",2.91]].map(([period,total])=>({period,label:`${period.slice(0,4)} 年 ${Number(period.slice(5))} 月`,up:total*.18*1024**4,down:total*.82*1024**4,total:total*1024**4})),
  years: [{period:"2026",label:"2026 年",up:3.4*1024**4,down:15.3*1024**4,total:18.7*1024**4},{period:"2025",label:"2025 年",up:7.2*1024**4,down:34*1024**4,total:41.2*1024**4}],
};

const SERVICE_VISUALS = {
  openai: [OpenAiLogo, "#4d83f3"], telegram: [TelegramLogo, "#35b89b"], x: [XLogo, "#269cd0"], github: [GithubLogo, "#9ba6b8"], microsoft: [WindowsLogo, "#5f82dd"], apple: [AppleLogo, "#bd8f3c"], direct: [Globe, "#48c59d"], globe: [Globe, "#66758d"], google: [GoogleLogo, "#55a36b"], youtube: [YoutubeLogo, "#ef5350"], cloudflare: [Globe, "#f39a34"],
};

function analysisDemoFor(groupBy, metric) {
  const proxyItems = ANALYSIS_DEMO.items.filter(item => item.id !== "Direct IP");
  const source = groupBy === "target" ? proxyItems.flatMap(item => item.details?.length ? item.details.map(detail => ({ id: detail.host, name: detail.host, icon: item.icon, ...detail, traffic: detail.up + detail.down, details: [] })) : [{ ...item, name: item.name.toLowerCase().replaceAll(" ", "") + ".com", details: [] }]) : proxyItems;
  const denominator = metric === "connections" ? source.reduce((sum, item) => sum + item.connections, 0) : source.reduce((sum, item) => sum + item.traffic, 0);
  const items = source.map(item => ({ ...item, percent: denominator ? Math.round((metric === "connections" ? item.connections : item.traffic) / denominator * 1000) / 10 : 0 })).sort((a,b) => (metric === "connections" ? b.connections - a.connections : b.traffic - a.traffic));
  return { ...ANALYSIS_DEMO, items };
}

function ServiceIcon({ type }) {
  const [Icon, color] = SERVICE_VISUALS[type] || SERVICE_VISUALS.globe;
  return <span className="service-icon" style={{ color }}><Icon weight="fill" /></span>;
}

const serviceDisplayName = (name) => name === "Direct IP" ? "IP 地址" : name;

const DEVICE_COLORS = ["#3f7df0", "#42bd96", "#a76aeb", "#f4b534", "#ef6e83", "#39a8d8"];

function UsageTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><strong>{label}</strong>{payload.filter(item => item.value).map(item => <span key={item.dataKey} style={{ color: item.color }}>{item.name} {bytes(item.value)}</span>)}</div>;
}

function AuditPage({ data }) {
  const [rangeKey, setRangeKey] = useState("month");
  const [device, setDevice] = useState("");
  const [groupBy, setGroupBy] = useState("service");
  const emptyAnalysis = { items: [], totals: { up: 0, down: 0, traffic: 0, proxy: 0, direct: 0 }, attribution: { service: "", devices: [], buckets: [] } };
  const [analysis, setAnalysis] = useState(DEMO_MODE ? ANALYSIS_DEMO : emptyAnalysis);
  const [selectedService, setSelectedService] = useState(DEMO_MODE ? "OpenAI" : "");
  const [attributionPeriod, setAttributionPeriod] = useState("day");
  const [historyPeriod, setHistoryPeriod] = useState("month");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(DEMO_MODE ? DEMO_USAGE_HISTORY : { months: [], years: [] });
  const [message, setMessage] = useState("");
  const load = async () => {
    setLoading(true);
    try {
      const result = await api.trafficAnalysis({ range: rangeKey, device, groupBy, metric: "traffic", service: selectedService, attributionPeriod });
      setAnalysis(result); setMessage("");
      if (result.attribution?.service) setSelectedService(result.attribution.service);
    } catch (error) { if (DEMO_MODE) setAnalysis(analysisDemoFor(groupBy, "traffic")); else setMessage(error.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [rangeKey, device, groupBy, selectedService, attributionPeriod]);
  useEffect(() => { api.trafficHistory().then(setHistory).catch(error => { if (!DEMO_MODE) setMessage(error.message); }); }, []);
  const items = analysis.items || [];
  const totals = analysis.totals || ANALYSIS_DEMO.totals;
  const proxyTotal = totals.proxy ?? items.reduce((sum, item) => sum + item.traffic, 0);
  const directTotal = totals.direct ?? Math.max(0, totals.traffic - proxyTotal);
  const totalTraffic = totals.traffic || proxyTotal + directTotal;
  const proxyPercent = totalTraffic ? proxyTotal / totalTraffic * 100 : 0;
  const directPercent = totalTraffic ? directTotal / totalTraffic * 100 : 0;
  const attribution = analysis.attribution || ANALYSIS_DEMO.attribution;
  const attributionDevices = attribution.devices || [];
  const attributionChart = (attribution.buckets || []).map(bucket => ({ time: bucket.time, ...bucket.values }));
  const selectedItem = items.find(item => item.name === selectedService) || items[0];
  const historySource = historyPeriod === "month" ? (history.months || []).slice(0, 13) : (history.years || []).slice(0, 8);
  const historyChart = [...historySource].reverse().map(item => ({ ...item, time: historyPeriod === "month" ? item.period : item.label }));
  return <div className="page-content traffic-analysis-page">
    {message && <div className="inline-message is-error"><WarningCircle />{message}</div>}
    <div className="analysis-toolbar"><div className="range-tabs">{DASHBOARD_RANGES.map(([id,label])=><button className={rangeKey===id?"active":""} key={id} onClick={()=>setRangeKey(id)}>{label}</button>)}</div><select value={device} onChange={event=>setDevice(event.target.value)}><option value="">全部设备</option>{data.devices.map(item=><option key={item.ip} value={item.ip}>{item.name} · {item.ip}</option>)}</select><button className="refresh-analysis" onClick={load}><ClockCounterClockwise />{loading ? "加载中" : "刷新"}</button></div>
    <section className="traffic-composition panel"><div className="composition-total"><span>总流量</span><strong>{bytes(totalTraffic)}</strong></div><div className="composition-ring" style={{"--proxy-share":`${proxyPercent * 3.6}deg`}}><i /></div><div className="composition-metric proxy"><span><i />代理流量</span><strong>{bytes(proxyTotal)}</strong><b>{proxyPercent.toFixed(1)}%</b><em>下载 {bytes(totals.proxyDown ?? 0)} · 上传 {bytes(totals.proxyUp ?? 0)}</em></div><div className="composition-metric direct"><span><i />直连流量</span><strong>{bytes(directTotal)}</strong><b>{directPercent.toFixed(1)}%</b></div><div className="composition-devices"><span>涉及设备</span><strong>{totals.proxyDevices ?? (attributionDevices.length || data.devices.length)} 台</strong></div></section>
    <div className="analysis-workspace">
      <section className="service-ranking panel"><div className="compact-panel-head"><h3>代理服务 / 目标排行</h3><div className="analysis-toggle"><button className={groupBy==="service"?"active":""} onClick={()=>setGroupBy("service")}>服务</button><button className={groupBy==="target"?"active":""} onClick={()=>setGroupBy("target")}>目标</button></div></div><div className="ranking-columns"><div className="ranking-list">{items.slice(0,7).map((item,index)=><button className={selectedItem?.id===item.id?"selected":""} key={item.id} onClick={()=>setSelectedService(item.service || item.name)}><b>{index+1}</b><ServiceIcon type={item.icon}/><span><strong>{serviceDisplayName(item.name)}</strong><em>{item.details?.length || 0} 个主机</em></span><span className="ranking-value"><strong>{bytes(item.traffic)}</strong><em>{item.percent}%</em></span></button>)}</div><div className="host-ranking"><h4>{serviceDisplayName(selectedItem?.name || "服务")} 相关主机</h4>{(selectedItem?.details || []).slice(0,6).map(detail=><div key={detail.host}><code>{detail.host}</code><strong>{bytes(detail.up + detail.down)}</strong></div>)}<div className="host-total"><span>合计</span><strong>{bytes(selectedItem?.traffic || 0)}</strong></div></div></div></section>
      <section className="device-attribution panel"><div className="compact-panel-head"><h3>{attribution.service || selectedItem?.name || "服务"} · 来源设备用量</h3><div className="analysis-toggle">{[["hour","按小时"],["day","按天"],["month","按月"]].map(([id,label])=><button key={id} className={attributionPeriod===id?"active":""} onClick={()=>setAttributionPeriod(id)}>{label}</button>)}</div></div><div className="attribution-body"><div className="attribution-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={attributionChart} margin={{top:12,right:4,left:-10,bottom:0}}><CartesianGrid stroke="var(--grid)" vertical={false}/><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={11}/><YAxis tickFormatter={bytes} tickLine={false} axisLine={false} fontSize={11} width={58}/><Tooltip content={<UsageTooltip/>}/>{attributionDevices.map((entry,index)=><Bar key={entry.ip} dataKey={entry.ip} name={entry.name} stackId="usage" fill={DEVICE_COLORS[index%DEVICE_COLORS.length]} isAnimationActive={false}/>)}</BarChart></ResponsiveContainer></div><div className="device-usage-table"><div className="device-usage-head"><span>设备</span><span>IP 地址</span><span>累计</span><span>占比</span></div>{attributionDevices.map((entry,index)=><div className="device-usage-row" key={entry.ip}><span><i style={{background:DEVICE_COLORS[index%DEVICE_COLORS.length]}}/>{entry.name}</span><code>{entry.ip}</code><strong>{bytes(entry.traffic)}</strong><b>{entry.percent}%</b></div>)}<div className="device-usage-total"><span>合计</span><strong>{bytes(attributionDevices.reduce((sum,item)=>sum+item.traffic,0))}</strong><b>100%</b></div></div></div></section>
    </div>
    <section className="proxy-history panel"><div className="compact-panel-head"><h3>代理流量历史用量</h3><div className="analysis-toggle"><button className={historyPeriod==="month"?"active":""} onClick={()=>setHistoryPeriod("month")}>月度</button><button className={historyPeriod==="year"?"active":""} onClick={()=>setHistoryPeriod("year")}>年度</button></div></div><div className="history-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={historyChart} margin={{top:24,right:12,left:4,bottom:0}}><CartesianGrid stroke="var(--grid)" vertical={false}/><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={11}/><YAxis tickFormatter={bytes} tickLine={false} axisLine={false} fontSize={11} width={60}/><Tooltip content={<UsageTooltip/>}/><Bar dataKey="down" name="下载" stackId="history" fill="#3f7df0" isAnimationActive={false}/><Bar dataKey="up" name="上传" stackId="history" fill="#a76aeb" radius={[3,3,0,0]} isAnimationActive={false}/></BarChart></ResponsiveContainer></div></section>
  </div>;
}

function StrategiesPage({ strategies, onChanged, canManage }) {
  const [expanded, setExpanded] = useState(() => new Set((strategies.primary || []).slice(0, 3).map(group => group.id)));
  const [secondaryExpanded, setSecondaryExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [reconnect, setReconnect] = useState(true);
  const [pending, setPending] = useState({});
  const select = async (group, name) => {
    setPending(current => ({ ...current, [group.id]: name }));
    setMessage(`正在切换 ${group.name}…`);
    try {
      const result = await api.selectStrategy(group.id, name, reconnect);
      const reconnectCopy = reconnect
        ? result.snapshotAvailable === false ? "策略已生效，但未能读取待重连会话。" : result.affectedConnections ? `已终止 ${result.closedConnections} 条受影响连接，应用会自动重连。` : "当前没有使用该策略的活跃连接。"
        : "现有连接保持不变，新连接会使用该策略。";
      setMessage(`${group.name} 已切换（${result.elapsedMs} ms）。${reconnectCopy}`);
      await onChanged();
    } catch (error) { setMessage(error.message); }
    finally { setPending(current => { const next = { ...current }; delete next[group.id]; return next; }); }
  };
  const delayChip = (item) => <span className={`latency-chip ${item.delayLevel || "unavailable"}`}><i />{item.delay || "待测速"}</span>;
  const regionNodes = (group) => {
    const unique = new Map();
    group.children?.forEach(child => child.members?.forEach(member => {
      const existing = unique.get(member.id);
      unique.set(member.id, existing ? { ...existing, ...member, selected: existing.selected || member.selected } : member);
    }));
    return [...unique.values()];
  };
  const toggle = (id) => setExpanded(current => {
    const next = new Set(current);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });
  const memberKind = (group, member) => group.children?.find(child => child.id === member.id)?.modeLabel || (member.id === "DIRECT" ? "直连" : "节点");
  const memberDelay = (group, member) => group.children?.find(child => child.id === member.id) || member;
  const memberCard = (group, member) => {
    const chosen = (pending[group.id] ?? group.nowId) === member.id;
    const automatic = group.children?.find(child => child.id === member.id);
    const disabled = !group.selectable || !canManage || Boolean(pending[group.id]);
    return <button
      type="button"
      className={`proxy-node-card ${chosen ? "selected" : ""} ${automatic ? "automatic" : ""}`}
      key={member.id}
      disabled={disabled}
      onClick={() => select(group, member.id)}
      title={disabled && !canManage ? "当前账户只有查看权限" : `切换到 ${member.name}`}
    >
      <span className="proxy-node-top"><strong>{member.name}</strong>{chosen && <CheckCircle weight="fill" />}</span>
      <span className="proxy-node-meta">{delayChip(memberDelay(group, member))}</span>
      {automatic && <span className="proxy-node-foot"><span>{automatic.type === "LoadBalance" ? `${automatic.health?.available || 0}/${automatic.health?.total || 0} 可用` : automatic.now}</span></span>}
    </button>;
  };
  const strategySection = (group) => {
    const nodes = regionNodes(group);
    const open = expanded.has(group.id) || Boolean(query);
    const members = (group.members || []).filter(member => !query || `${member.name} ${group.name}`.toLowerCase().includes(query.toLowerCase()));
    if (query && !members.length && !nodes.some(node => node.name.toLowerCase().includes(query.toLowerCase()))) return null;
    return <section className={`proxy-group panel ${open ? "is-open" : ""}`} key={group.id}>
      <button className="proxy-group-head" onClick={() => toggle(group.id)} type="button">
        <span className="proxy-group-icon"><ArrowsDownUp weight="bold" /></span>
        <span className="proxy-group-title"><span><b>{group.name}</b><em>{group.typeLabel}</em><small>{group.members?.length || 0}</small></span><span>当前出口 <strong>{pending[group.id] ? `正在切换至 ${pending[group.id]}` : group.now}</strong></span></span>
        <span className="proxy-group-health"><small>{group.health?.available ?? group.members?.length ?? 0}/{group.health?.total ?? group.members?.length ?? 0} 可用</small>{delayChip(group)}</span>
        <CaretDown className={open ? "rotated" : ""} />
      </button>
      {open && <div className="proxy-group-body">
        <div className="proxy-member-grid">{members.map(member => memberCard(group, member))}</div>
        {nodes.length > 0 && <div className="proxy-health-block">
          <div className="proxy-health-title"><span><WifiHigh /> 节点健康</span><small>{nodes.filter(node => node.alive).length}/{nodes.length} 在线</small></div>
          <div className="proxy-health-grid">{nodes.filter(node => !query || node.name.toLowerCase().includes(query.toLowerCase())).map(node => <div className={`proxy-health-node ${node.selected ? "selected" : ""} ${node.alive === false ? "offline" : ""}`} key={node.id}><span className="node-status" /><span><strong title={node.name}>{node.name}</strong></span>{delayChip(node)}</div>)}</div>
        </div>}
      </div>}
    </section>;
  };
  return (
    <div className="page-content strategies-page">
      <div className="proxy-workbench-head"><h2>分流策略</h2><div className="proxy-workbench-actions"><label className="proxy-search"><MagnifyingGlass /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索策略或节点" /></label>{canManage && <label className="reconnect-toggle"><input type="checkbox" checked={reconnect} onChange={event => setReconnect(event.target.checked)} /><span><strong>切换后重连</strong></span></label>}</div></div>
      <div className="proxy-summary-strip"><span><ArrowsDownUp />{strategies.primary.length} 个常用策略</span></div>
      {message && <div className="inline-message strategy-message">{message}</div>}
      <div className="proxy-groups">{strategies.primary.map(strategySection)}</div>
      <button className="collapsed-groups proxy-secondary-toggle" onClick={() => setSecondaryExpanded(!secondaryExpanded)}><span><Stack />其他规则策略</span><small>{strategies.secondaryCount} 个</small><CaretDown className={secondaryExpanded ? "rotated" : ""}/></button>
      {secondaryExpanded && <div className="secondary-grid">{strategies.secondary.filter(group => !query || `${group.name} ${group.now}`.toLowerCase().includes(query.toLowerCase())).map(group=><div className="secondary-group" key={group.name}><span>{group.name}</span><strong>{group.now}</strong></div>)}</div>}
    </div>
  );
}

const emptyRuleSet = { name: "", url: "", policy: "", enabled: true, interval: 86400, behavior: "classical", format: "text" };
const demoRuleWorkspace = {
  revision: 1, appliedRevision: 0, dirty: true, counts: { ruleSets: 37, enabledRuleSets: 37, customRules: 0 },
  availablePolicies: ["🚀 节点选择", "🇺🇸 美国", "🇯🇵 日本", "🎯 全球直连", "🛑 全球拦截", "💬 Ai平台", "DIRECT"],
  fallbackRules: [{ type: "GEOIP", policy: "🎯 全球直连", content: "GEOIP,CN,🎯 全球直连" }, { type: "MATCH", policy: "🐟 漏网之鱼", content: "MATCH,🐟 漏网之鱼" }],
  customRules: [],
  ruleSets: [
    ["legacy-us", "美国域名", "us.list", "🇺🇸 美国"], ["legacy-gfw", "GFW 列表", "ProxyGFWlist.list", "🚀 节点选择"], ["legacy-download", "下载工具", "Download.list", "🎯 全球直连"], ["legacy-apple-cn", "苹果中国", "Apple.list", "🎯 全球直连"], ["legacy-jp", "日本域名", "jp.list", "🇯🇵 日本"], ["legacy-direct", "直连域名", "direct.list", "DIRECT"], ["legacy-lan", "局域网", "LocalAreaNetwork.list", "🎯 全球直连"], ["legacy-ad", "广告拦截", "BanAD.list", "🛑 全球拦截"], ["legacy-ai", "AI 平台", "AI.list", "💬 Ai平台"],
  ].map(([id,name,path,policy]) => ({ id, providerId: `demo-${id}`, name, url: `https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/${path}`, policy, enabled: true, interval: 86400, behavior: "classical", format: "text" })),
};

function RulesPage({ canManage }) {
  const [workspace, setWorkspace] = useState(null);
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [setEditor, setSetEditor] = useState(null);
  const [customEditor, setCustomEditor] = useState(null);
  const load = async () => {
    try { setWorkspace(await api.ruleWorkspace()); }
    catch (error) { if (DEMO_MODE) setWorkspace(demoRuleWorkspace); else setMessage(error.message); }
  };
  useEffect(() => { load(); }, []);
  const run = async (action, success) => {
    setBusy(true); setMessage("");
    try { await action(); await load(); setMessage(success); return true; }
    catch (error) { setMessage(error.message); return false; }
    finally { setBusy(false); }
  };
  const saveSet = async (event) => {
    event.preventDefault();
    const { id, providerId, ...payload } = setEditor;
    if (await run(() => id ? api.updateRuleSet(id, payload) : api.createRuleSet(payload), id ? "规则集已更新，应用后生效。" : "规则集已添加，应用后生效。")) setSetEditor(null);
  };
  const saveCustom = async (event) => {
    event.preventDefault();
    const { id, ...payload } = customEditor;
    if (await run(() => id ? api.updateCustomRule(id, payload) : api.createCustomRule(payload), id ? "自定义规则已更新。" : "自定义规则已添加。")) setCustomEditor(null);
  };
  const sourceHost = (url) => { try { return new URL(url).hostname; } catch { return "无效地址"; } };
  const sets = (workspace?.ruleSets || []).filter(item => !query || `${item.name} ${item.url} ${item.policy}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-content rules-page">
    <div className="rules-hero"><h2>规则管理</h2><div className="rules-actions">{canManage && <button className="filter-button" disabled={busy} onClick={() => setSetEditor({ ...emptyRuleSet, policy: workspace?.availablePolicies?.[0] || "" })}>添加规则集</button>}{canManage && <button className="filter-button" disabled={busy} onClick={() => setCustomEditor({ content: "DOMAIN-SUFFIX,example.com,DIRECT", placement: "before", note: "", enabled: true })}>添加单条规则</button>}{canManage && <button className="filter-button" disabled={busy || !workspace?.appliedRevision} onClick={() => run(() => Promise.all((workspace?.ruleSets || []).filter(item => item.enabled).map(item => api.refreshRuleSet(item.id))), "所有已启用规则集均已刷新。")}>刷新规则源</button>}{canManage && <button className="primary-button" disabled={busy || !workspace?.dirty} onClick={() => run(api.applyRules, "规则已校验并热重载到网关。")}>{busy ? "处理中…" : workspace?.dirty ? "应用更改" : "已应用"}</button>}</div></div>
    {message && <div className="inline-message">{message}</div>}
    <div className="rule-stat-grid"><div><span>规则集</span><strong>{workspace?.counts?.ruleSets ?? "—"}</strong></div><div><span>自定义规则</span><strong>{workspace?.counts?.customRules ?? "—"}</strong></div><div><span>工作区版本</span><strong>r{workspace?.revision ?? "—"}</strong></div><div><span>安全兜底</span><strong>{workspace?.fallbackRules?.at(-1)?.policy || "—"}</strong></div></div>
    <section className="panel rule-set-panel"><div className="rule-toolbar"><h3>有序规则集</h3><label className="search-box"><MagnifyingGlass /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索名称、来源或目标策略" />{query && <button onClick={() => setQuery("")}><X /></button>}</label></div><div className="rule-set-head"><span>顺序 / 状态</span><span>规则集</span><span>目标策略</span><span>更新周期</span><span>操作</span></div><div className="rule-set-list">{sets.map((item, visibleIndex) => { const index = workspace.ruleSets.findIndex(row => row.id === item.id); return <div className={`rule-set-row ${!item.enabled ? "disabled" : ""}`} key={item.id}><span className="rule-order"><b>{String(index + 1).padStart(2,"0")}</b><label className="rule-switch"><input type="checkbox" disabled={!canManage || busy} checked={item.enabled} onChange={event => run(() => api.updateRuleSet(item.id, { enabled: event.target.checked }), event.target.checked ? "规则集已启用，应用后生效。" : "规则集已停用，应用后生效。")} /><i /></label></span><span className="rule-set-name"><strong>{item.name}</strong><small>{sourceHost(item.url)} · {item.behavior}/{item.format}</small></span><span><b className="policy-chip">{item.policy.replace(/^[^A-Za-z0-9\u3400-\u9fff]+/, "")}</b></span><span className="rule-interval">{Math.round(item.interval / 3600)} 小时</span><span className="rule-row-actions">{canManage && <><button disabled={busy || index === 0 || query} title="上移" onClick={() => run(() => api.moveRuleSet(item.id,"up"), "顺序已调整，应用后生效。")}>↑</button><button disabled={busy || index === workspace.ruleSets.length - 1 || query} title="下移" onClick={() => run(() => api.moveRuleSet(item.id,"down"), "顺序已调整，应用后生效。")}>↓</button><button onClick={() => setSetEditor({ ...item })}>编辑</button><button className="danger-link" onClick={() => confirm(`删除规则集「${item.name}」？`) && run(() => api.deleteRuleSet(item.id), "规则集已删除，应用后生效。")}>删除</button></>}</span></div>; })}</div></section>
    <section className="panel custom-rules-panel"><div className="panel-heading"><h2>自定义覆盖规则</h2></div>{workspace?.customRules?.length ? <div className="custom-rule-list">{workspace.customRules.map(rule => <div className={!rule.enabled ? "disabled" : ""} key={rule.id}><label className="rule-switch"><input type="checkbox" disabled={!canManage} checked={rule.enabled} onChange={event => run(() => api.updateCustomRule(rule.id,{ enabled:event.target.checked }), "规则状态已更新。")}/><i /></label><span className="rule-placement">{rule.placement === "after" ? "后置" : "前置"}</span><code>{rule.content}</code><span className="policy-chip">{rule.policy}</span>{canManage && <span className="rule-row-actions"><button onClick={() => setCustomEditor({ ...rule })}>编辑</button><button className="danger-link" onClick={() => confirm("删除这条自定义规则？") && run(() => api.deleteCustomRule(rule.id), "自定义规则已删除。")}>删除</button></span>}</div>)}</div> : <div className="empty-rules">还没有自定义规则</div>}</section>
    {setEditor && <div className="modal-backdrop" onMouseDown={() => setSetEditor(null)}><form className="user-modal rule-modal" onMouseDown={event => event.stopPropagation()} onSubmit={saveSet}><div className="modal-heading"><div><span className="eyebrow">规则集</span><h3>{setEditor.id ? "编辑规则集" : "添加规则集"}</h3></div><button type="button" onClick={() => setSetEditor(null)}><X /></button></div><label>名称<input required value={setEditor.name} onChange={event => setSetEditor({...setEditor,name:event.target.value})}/></label><label>远程地址<input required type="url" value={setEditor.url} onChange={event => setSetEditor({...setEditor,url:event.target.value})}/></label><label>目标策略<select value={setEditor.policy} onChange={event => setSetEditor({...setEditor,policy:event.target.value})}>{workspace.availablePolicies.map(policy => <option key={policy} value={policy}>{policy}</option>)}</select></label><div className="modal-fields"><label>更新周期（秒）<input type="number" min="300" value={setEditor.interval} onChange={event => setSetEditor({...setEditor,interval:Number(event.target.value)})}/></label><label>内容格式<select value={setEditor.format} onChange={event => setSetEditor({...setEditor,format:event.target.value})}><option value="text">text</option><option value="yaml">yaml</option><option value="mrs">mrs</option></select></label></div><button className="primary-button modal-submit" disabled={busy}>保存到工作区</button></form></div>}
    {customEditor && <div className="modal-backdrop" onMouseDown={() => setCustomEditor(null)}><form className="user-modal rule-modal" onMouseDown={event => event.stopPropagation()} onSubmit={saveCustom}><div className="modal-heading"><div><span className="eyebrow">请求匹配</span><h3>{customEditor.id ? "编辑自定义规则" : "添加自定义规则"}</h3></div><button type="button" onClick={() => setCustomEditor(null)}><X /></button></div><label>规则内容<input required value={customEditor.content} onChange={event => setCustomEditor({...customEditor,content:event.target.value})} placeholder="DOMAIN-SUFFIX,example.com,节点选择"/><small>使用 mihomo 规则语法；保存后会解析并在应用时校验策略引用。</small></label><label>位置<select value={customEditor.placement} onChange={event => setCustomEditor({...customEditor,placement:event.target.value})}><option value="before">规则集之前（高优先级）</option><option value="after">规则集之后（低优先级）</option></select></label><label>备注<input value={customEditor.note || ""} onChange={event => setCustomEditor({...customEditor,note:event.target.value})}/></label><button className="primary-button modal-submit" disabled={busy}>保存到工作区</button></form></div>}
  </div>;
}

const shanghaiTime = (timestamp) => timestamp ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(timestamp * 1000)) : "尚无记录";

function GatewayPage({ canManage }) {
  const [aliases, setAliases] = useState({});
  const [devices, setDevices] = useState([]);
  const [message, setMessage] = useState("");
  useEffect(() => { api.deviceAliases().then(result => { setAliases(result.aliases || {}); setDevices(result.devices || []); }).catch(error => setMessage(error.message)); }, []);
  const save = async () => {
    try { const result = await api.saveDeviceAliases(aliases); setAliases(result.aliases); setMessage("设备名称已保存，仪表盘会在下一次采样时更新。"); }
    catch (error) { setMessage(error.message); }
  };
  const known = [...new Map(devices.map(device => [device.ip, device])).values()];
  return <div className="page-content gateway-page"><div className="strategy-intro"><h2>网关与代理设备</h2>{canManage && <button className="primary-button" onClick={save}><CheckCircle /> 保存设备名称</button>}</div>{message && <div className="inline-message">{message}</div>}<section className="panel gateway-summary"><div><span>默认网关</span><strong>192.168.31.190</strong></div><div><span>透明 DNS</span><strong>198.18.0.2</strong></div><div><span>运行模式</span><strong>TUN + 显式代理</strong></div></section><section className="panel managed-devices"><div className="panel-heading"><h2>已识别设备</h2></div><div className="device-editor-head"><span>来源 IP</span><span>设备名称</span><span>接入方式</span><span>活跃连接</span><span>最后活动</span></div>{known.map(device => <div className="device-editor-row" key={device.ip}><code>{device.ip}</code><input disabled={!canManage} value={aliases[device.ip] ?? device.name ?? ""} onChange={event => setAliases(current => ({ ...current, [device.ip]: event.target.value }))} /><span className={`device-source ${device.sourceType || "unknown"}`}><i />{device.sourceType === "proxy" ? "显式代理" : device.sourceType === "gateway" ? "局域网网关" : "未知"}</span><span className={device.active ? "device-active" : "device-idle"}>{device.active || 0}</span><time>{device.active ? "正在活动" : shanghaiTime(device.lastSeen)}</time></div>)}</section></div>;
}

const DEMO_SUBSCRIPTIONS = {
  subscriptions: [{
    id: "demo-g94", owner: "demo", name: "G94Cloud", maskedUrl: "https://www.g94cloud.com/••••",
    interval: 21600, enabled: true, gatewayEnabled: true, sourceFormat: "surge", nodeCount: 16,
    usage: { upload: 31 * 1024 ** 3, download: 202 * 1024 ** 3, total: 687 * 1024 ** 3, expire: Date.parse("2026-08-31T21:48:00+08:00") / 1000 },
    fetchedAt: Date.parse("2026-08-12T23:15:00+08:00") / 1000, lastError: null,
    deliveryPaths: { surge: "#demo-surge", clash: "#demo-clash" },
  }],
  summary: { count: 1, nodes: 16, healthy: 1, gateway: "G94Cloud" },
};

function SubscriptionsPage({ user }) {
  const [data, setData] = useState({ subscriptions: [], summary: { count: 0, nodes: 0, healthy: 0, gateway: null } });
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);
  const [openMenu, setOpenMenu] = useState("");
  const load = async () => {
    try { setData(await api.subscriptions()); setError(false); }
    catch (caught) {
      if (DEMO_MODE) { setData(DEMO_SUBSCRIPTIONS); setMessage(""); setError(false); }
      else { setMessage(caught.message); setError(true); }
    }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const closeMenu = event => {
      if (!event.target.closest(".subscription-menu")) setOpenMenu("");
    };
    const closeOnEscape = event => { if (event.key === "Escape") setOpenMenu(""); };
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  const run = async (key, action, success) => {
    setBusy(key); setMessage(""); setError(false);
    try { const result = await action(); await load(); setMessage(typeof success === "function" ? success(result) : success); return true; }
    catch (caught) { setMessage(caught.message); setError(true); return false; }
    finally { setBusy(""); }
  };
  const save = async (event) => {
    event.preventDefault();
    const payload = { name: editor.name, interval: Number(editor.interval), enabled: editor.enabled };
    if (!editor.id || editor.url) payload.url = editor.url;
    const ok = await run(editor.id || "create", () => editor.id ? api.updateSubscription(editor.id, payload) : api.createSubscription(payload), result => result.subscription?.lastError ? `订阅已保存，但首次拉取失败：${result.subscription.lastError}` : editor.id ? "订阅设置已更新。" : "订阅已添加并完成首次解析。");
    if (ok) setEditor(null);
  };
  const copyDelivery = async (item, client) => {
    const delivery = new URL(item.deliveryPaths?.[client], location.origin).toString();
    const label = client === "surge" ? "Surge" : "Clash/Mihomo";
    try { await navigator.clipboard.writeText(delivery); setMessage(`${label} 完整配置地址已复制。`); setError(false); }
    catch { setMessage(`复制失败，请手动复制：${delivery}`); setError(true); }
  };
  const items = data.subscriptions || [];
  return <div className="page-content subscriptions-page">
    <div className="subscriptions-hero"><h2>订阅与节点来源</h2><button className="primary-button" onClick={() => setEditor({ name: "", url: "", interval: 21600, enabled: true })}><Plus weight="bold" /> 添加订阅</button></div>
    {message && <div className={`inline-message ${error ? "is-error" : ""}`}>{error ? <WarningCircle /> : <CheckCircle />}{message}</div>}
    <div className="subscription-stats"><div><span>订阅来源</span><strong>{data.summary?.count ?? 0}</strong></div><div><span>可用节点库存</span><strong>{data.summary?.nodes ?? 0}</strong></div><div><span>网关活动源</span><strong>{data.summary?.gateway || "未设置"}</strong></div><div><span>自动刷新</span><strong>{items.filter(item => item.enabled).length}</strong></div></div>
    <section className="panel subscription-panel">
      <div className="subscription-panel-head"><h3>订阅列表</h3><button className="filter-button" disabled={Boolean(busy)} onClick={() => run("all", async () => { for (const item of items.filter(row => row.enabled)) await api.refreshSubscription(item.id); }, "所有已启用订阅均已刷新。") }><ArrowClockwise /> 刷新全部</button></div>
      {items.length ? <div className="subscription-list">{items.map(item => {
        const used = Number(item.usage?.upload || 0) + Number(item.usage?.download || 0);
        const total = Number(item.usage?.total || 0);
        const percent = total ? Math.min(100, used / total * 100) : 0;
        return <article className={`subscription-card ${item.gatewayEnabled ? "is-gateway" : ""}`} key={item.id}>
          <div className="subscription-card-toolbar">
            {user?.role === "admin" ? <button className={`subscription-gateway-status ${item.gatewayEnabled ? "active" : ""}`} disabled={Boolean(busy) || (!item.gatewayEnabled && !item.nodeCount)} onClick={() => run(`gateway-${item.id}`, () => item.gatewayEnabled ? api.deactivateSubscription(item.id) : api.activateSubscription(item.id), item.gatewayEnabled ? "已停用订阅覆盖，网关恢复基础节点配置。" : "订阅已成为网关节点源，并已热重载。") }><span />{item.gatewayEnabled ? "网关使用中" : "用于网关"}</button> : <span className={`subscription-gateway-status ${item.gatewayEnabled ? "active" : ""}`}><span />{item.gatewayEnabled ? "网关使用中" : "个人订阅"}</span>}
            <div className="subscription-menu">
              <button className="subscription-menu-trigger" aria-label={`管理 ${item.name}`} aria-expanded={openMenu === item.id} onClick={event => { event.stopPropagation(); setOpenMenu(current => current === item.id ? "" : item.id); }}><DotsThreeVertical weight="bold" /></button>
              {openMenu === item.id && <div className="subscription-menu-popover" role="menu">
                <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(""); run(item.id, () => api.refreshSubscription(item.id), "订阅已刷新；节点库存与状态已更新。"); }}><ArrowClockwise className={busy === item.id ? "spinning" : ""} />立即刷新</button>
                <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(""); setEditor({ id: item.id, name: item.name, url: "", interval: item.interval, enabled: item.enabled }); }}><PencilSimple />编辑订阅</button>
                <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(""); if (confirm(`轮换「${item.name}」的交付链接？旧链接会立即失效。`)) run(`rotate-${item.id}`, () => api.rotateSubscriptionToken(item.id), "交付链接已轮换，旧链接已失效。"); }}><LinkSimple />轮换交付链接</button>
                <button role="menuitem" className="danger" disabled={Boolean(busy)} onClick={() => { setOpenMenu(""); if (confirm(`删除订阅「${item.name}」？交付地址将立即失效。`)) run(`delete-${item.id}`, () => api.deleteSubscription(item.id), "订阅已删除。"); }}><Trash />删除订阅</button>
              </div>}
            </div>
          </div>
          <div className="subscription-source"><span className={`subscription-health ${item.lastError ? "failed" : item.fetchedAt ? "healthy" : "pending"}`}><CloudArrowDown weight="fill" /></span><div><div className="subscription-title"><h3>{item.name}</h3>{item.gatewayEnabled && <b>网关节点源</b>}{user?.role === "admin" && item.owner !== user.username && <em>{item.owner}</em>}</div><p>{item.maskedUrl}</p><div className="subscription-node-count"><HardDrives /><strong>{item.nodeCount || 0}</strong><span>个节点</span>{item.lastError && <b>刷新失败</b>}</div></div></div>
          <div className="subscription-quota"><div className="subscription-quota-value"><strong>{total ? bytes(used) : "—"}</strong><span>{total ? `已用 / ${bytes(total)}` : "来源未提供配额"}</span></div><i><u style={{ width: `${percent}%` }} /></i>{total > 0 && <b>{percent.toFixed(1)}%</b>}<div className="subscription-lifecycle"><span><b>到期时间</b><time>{item.usage?.expire ? shanghaiTime(item.usage.expire) : "未提供"}</time></span><span><b>更新时间</b><time>{item.lastError ? "刷新失败" : shanghaiTime(item.fetchedAt)}</time></span></div></div>
          <div className="subscription-deliveries" aria-label={`${item.name} 配置链接`}>
            <div className="subscription-delivery"><AppleLogo weight="fill" /><span>Surge 配置</span><button title="复制 Surge 配置链接" onClick={() => copyDelivery(item, "surge")}><Copy /></button><a title="打开 Surge 配置" href={item.deliveryPaths?.surge} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
            <div className="subscription-delivery"><FileCode weight="fill" /><span>Clash / Mihomo</span><button title="复制 Clash/Mihomo 配置链接" onClick={() => copyDelivery(item, "clash")}><Copy /></button><a title="打开 Clash/Mihomo 配置" href={item.deliveryPaths?.clash} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
          </div>
          {item.lastError && <div className="subscription-error"><WarningCircle />{item.lastError}</div>}
        </article>;
      })}</div> : <div className="subscription-empty"><CloudArrowDown /><h3>还没有订阅</h3><p>添加节点来源后，可定时刷新、生成隔离交付地址；管理员还可以把它设为网关节点源。</p><button className="primary-button" onClick={() => setEditor({ name: "", url: "", interval: 21600, enabled: true })}>添加第一个订阅</button></div>}
    </section>
    {editor && <div className="modal-backdrop" onMouseDown={() => setEditor(null)}><form className="user-modal subscription-modal" onMouseDown={event => event.stopPropagation()} onSubmit={save}><div className="modal-heading"><div><span className="eyebrow">节点来源</span><h3>{editor.id ? "编辑订阅" : "添加订阅"}</h3></div><button type="button" onClick={() => setEditor(null)}><X /></button></div><label>名称<input required value={editor.name} onChange={event => setEditor({ ...editor, name: event.target.value })} placeholder="例如 G94Cloud" /></label><label>订阅地址<input required={!editor.id} type="url" value={editor.url} onChange={event => setEditor({ ...editor, url: event.target.value })} placeholder={editor.id ? "留空表示保留当前地址" : "https://example.com/subscribe"} /><small>地址视为凭据保存，不会在列表或 API 响应中明文返回。</small></label><div className="modal-fields"><label>刷新周期<select value={editor.interval} onChange={event => setEditor({ ...editor, interval: Number(event.target.value) })}><option value={3600}>1 小时</option><option value={21600}>6 小时</option><option value={43200}>12 小时</option><option value={86400}>24 小时</option><option value={604800}>7 天</option></select></label><label className="subscription-enabled">自动刷新<span><input type="checkbox" checked={editor.enabled} onChange={event => setEditor({ ...editor, enabled: event.target.checked })} />启用</span></label></div><button className="primary-button modal-submit" disabled={Boolean(busy)}>{busy ? "正在保存与解析…" : "保存订阅"}</button></form></div>}
  </div>;
}

function SystemPage() {
  const [users, setUsers] = useState(DEMO_MODE ? [{ id: 1, username: "admin", role: "admin", allowedDevices: [] }] : []);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ username: "", password: "", role: "viewer", devices: "" });

  useEffect(() => { api.users().then(result => setUsers(result.users)).catch(error => setMessage(error.message)); }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm({ username: "", password: "", role: "viewer", devices: "" });
    setShowForm(true);
  };
  const openEdit = (user) => {
    setEditingId(user.id);
    setForm({ username: user.username, password: "", role: user.role, devices: (user.allowedDevices || []).join(", ") });
    setShowForm(true);
  };
  const submit = async (event) => {
    event.preventDefault();
    setMessage("");
    try {
      const allowedDevices = form.devices.split(",").map(item => item.trim()).filter(Boolean);
      const payload = editingId
        ? { role: form.role, allowedDevices, ...(form.password ? { password: form.password } : {}) }
        : { username: form.username, password: form.password, role: form.role, allowedDevices };
      const result = editingId ? await api.updateUser(editingId, payload) : await api.createUser(payload);
      setUsers(current => editingId ? current.map(item => item.id === editingId ? result.user : item) : [...current, result.user]);
      setShowForm(false);
      setEditingId(null);
      setMessage(editingId ? "用户权限已更新。" : "用户已创建。");
    } catch (error) { setMessage(error.message); }
  };

  return <div className="page-content system-page">
    <div className="strategy-intro"><h2>用户与数据隔离</h2><button className="primary-button" onClick={openCreate}><Users /> 添加用户</button></div>
    {message && <div className="system-message"><ShieldCheck />{message}</div>}
    <section className="panel users-panel">
      <div className="users-head"><span>用户</span><span>角色</span><span>可见设备</span><span>权限 / 操作</span></div>
      {users.map(user => <div className="user-row" key={user.id}>
        <span className="user-identity"><span className="avatar">{user.username.slice(0,1).toUpperCase()}</span><strong>{user.username}</strong></span>
        <span><b className={`role-badge ${user.role}`}>{user.role === "admin" ? "管理员" : "普通用户"}</b></span>
        <span className="device-scope">{user.role === "admin" ? "全部设备" : user.allowedDevices.length ? user.allowedDevices.join("、") : "无设备"}</span>
        <span className="boundary-copy"><span>{user.role === "admin" ? "全局读写" : "授权设备只读"}</span><button type="button" onClick={() => openEdit(user)}>编辑</button></span>
      </div>)}
    </section>
    {showForm && <div className="modal-backdrop" onMouseDown={() => setShowForm(false)}>
      <form className="user-modal" onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
        <div className="modal-heading"><h3>{editingId ? "编辑用户" : "创建用户"}</h3><button type="button" onClick={() => setShowForm(false)}><X /></button></div>
        <label>用户名<input required minLength={3} disabled={Boolean(editingId)} value={form.username} onChange={event => setForm({...form, username:event.target.value})} /></label>
        <label>{editingId ? "新密码（留空不修改）" : "初始密码"}<input required={!editingId} minLength={12} type="password" value={form.password} onChange={event => setForm({...form, password:event.target.value})} /></label>
        <label>角色<select value={form.role} onChange={event => setForm({...form, role:event.target.value})}><option value="viewer">普通用户</option><option value="admin">管理员</option></select></label>
        {form.role === "viewer" && <label>可见设备 IP<input value={form.devices} onChange={event => setForm({...form, devices:event.target.value})} placeholder="192.168.31.28, 192.168.31.46" /></label>}
        <button className="primary-button modal-submit">{editingId ? "保存权限" : "创建用户"}</button>
      </form>
    </div>}
  </div>;
}

function LoginScreen({ onLogin, error, loading }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  return <main className="login-screen"><section className="login-card"><div className="login-brand"><span className="brand-mark"><Stack weight="fill" /></span><strong>Egresscope</strong></div><div className="login-copy"><h1>登录到网关控制台</h1></div><form onSubmit={(e)=>{e.preventDefault();onLogin(username,password)}}><label>用户名<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username"/></label><label>密码<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" autoFocus/></label>{error && <div className="login-error"><WarningCircle />{error}</div>}<button className="login-button" disabled={loading}>{loading ? "正在登录…" : "登录"}</button></form></section></main>;
}

function ServiceUnavailable({ message, retry }) {
  return <main className="login-screen"><section className="login-card"><div className="login-brand"><span className="brand-mark"><Stack weight="fill" /></span><strong>Egresscope</strong></div><div className="login-copy"><h1>控制面暂时不可用</h1></div><div className="login-error"><WarningCircle />{message || "无法连接到网关控制面"}</div><button className="login-button" onClick={retry}>重新连接</button></section></main>;
}

export function App() {
  const [page, setPage] = useState(() => new URLSearchParams(location.search).get("page") || "dashboard");
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("egresscope-theme") || localStorage.getItem("ssslab-theme") || "system");
  const [dashboard, setDashboard] = useState(DEMO_MODE ? demoDashboard : null);
  const [strategies, setStrategies] = useState(DEMO_MODE ? demoStrategies : { primary: [], secondary: [], secondaryCount: 0 });
  const [device, setDevice] = useState(null);
  const [auth, setAuth] = useState({ checked: false, required: false, user: null });
  const [login, setLogin] = useState({ loading: false, error: "" });
  const [backendError, setBackendError] = useState("");

  useEffect(() => {
    const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("egresscope-theme", theme);
  }, [theme]);

  useEffect(() => {
    let mounted = true;
    api.session().then((result) => {
      if (!mounted) return;
      setAuth({ checked: true, required: result.required, user: result.user });
    }).catch((error) => {
      if (DEMO_MODE) setAuth({ checked: true, required: false, user: { username: "demo", role: "admin" } });
      else { setBackendError(error.message); setAuth({ checked: true, required: true, user: null }); }
    });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!auth.checked || (auth.required && !auth.user)) return undefined;
    const load = async () => {
      try {
        setDashboard(await api.dashboard());
        setBackendError("");
      } catch (error) { if (!DEMO_MODE) setBackendError(error.message); }
      if (auth.user?.role === "admin") {
        try { setStrategies(await api.strategies()); }
        catch { /* Keep the last strategy snapshot while the gateway retries. */ }
      }
    };
    load();
    return subscribeLive((payload) => { setDashboard((current) => ({ ...(current || {}), ...payload })); setBackendError(""); }, (error) => { if (!DEMO_MODE) setBackendError(error.message); });
  }, [auth]);

  const selectDevice = async (selected) => {
    try { setDevice(await api.device(selected.ip)); }
    catch (error) { if (DEMO_MODE) setDevice({ ...demoDevice, ...selected }); else setBackendError(error.message); }
  };

  const doLogin = async (username, password) => {
    setLogin({ loading: true, error: "" });
    try {
      const result = await api.login(username, password);
      setAuth({ checked: true, required: true, user: result.user });
      setLogin({ loading: false, error: "" });
    } catch (error) { setLogin({ loading: false, error: error.message || "登录失败" }); }
  };

  const doLogout = async () => {
    try { await api.logout(); } catch (error) { if (!DEMO_MODE) setBackendError(error.message); }
    if (auth.required) setAuth({ checked: true, required: true, user: null });
  };

  const cycleTheme = () => setTheme((current) => current === "system" ? "light" : current === "light" ? "dark" : "system");
  const refreshStrategies = async () => setStrategies(await api.strategies());
  const visiblePage = canOpenPage(page, auth.user) ? page : "dashboard";
  const title = device ? ["设备分析", `${device.name} · ${device.ip}`] : PAGE_TITLES[visiblePage];
  const topbarSubtitle = null;

  if (!auth.checked) return <main className="login-screen" />;
  if (backendError && !auth.user) return <ServiceUnavailable message={backendError} retry={() => location.reload()} />;
  if (auth.required && !auth.user) return <LoginScreen onLogin={doLogin} {...login} />;
  if (!dashboard) return <ServiceUnavailable message={backendError} retry={() => location.reload()} />;

  return (
    <div className="app-shell">
      <Sidebar page={visiblePage} setPage={(next) => { setDevice(null); setPage(canOpenPage(next, auth.user) ? next : "dashboard"); }} collapsed={collapsed} setCollapsed={setCollapsed} user={auth.user} />
      <div className="main-shell">
        <Topbar title={title[0]} subtitle={topbarSubtitle} online={dashboard.status.online} theme={theme} cycleTheme={cycleTheme} onLogout={doLogout} user={auth.user} />
        <main className="main-content">
          {backendError && <div className="inline-message is-error"><WarningCircle />数据刷新失败：{backendError}</div>}
          {device ? <DeviceFlow device={device} onBack={() => setDevice(null)} /> : visiblePage === "dashboard" ? <Dashboard data={dashboard} strategies={strategies} onDevice={selectDevice} onNavigate={setPage} canManage={auth.user?.role === "admin"} /> : visiblePage === "connections" ? <ConnectionsPage data={dashboard} onDevice={selectDevice} canManage={auth.user?.role === "admin"} /> : visiblePage === "audit" ? <AuditPage data={dashboard} /> : visiblePage === "strategies" ? <StrategiesPage strategies={strategies} onChanged={refreshStrategies} canManage /> : visiblePage === "rules" ? <RulesPage canManage /> : visiblePage === "subscriptions" ? <SubscriptionsPage user={auth.user} /> : visiblePage === "gateway" ? <GatewayPage canManage /> : visiblePage === "system" ? <SystemPage /> : <Dashboard data={dashboard} strategies={strategies} onDevice={selectDevice} onNavigate={setPage} canManage={auth.user?.role === "admin"} />}
        </main>
      </div>
    </div>
  );
}
