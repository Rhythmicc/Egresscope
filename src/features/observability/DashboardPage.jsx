import { useEffect, useState } from "react";
import {
  CaretDown,
  ChartDonut,
  CheckCircle,
  CloudArrowDown,
  Funnel,
  GlobeHemisphereEast,
  HardDrives,
  Pulse,
} from "@phosphor-icons/react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../../api";
import { bucketDuration, bytes, rate } from "../../lib/formatters";

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

export function TrafficChart({ data, compact = false }) {
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

export const DASHBOARD_RANGES = [
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

function ConnectionStatisticsTable({ connections, onSelect, onContext, dense = false }) {
  return <div className={`connection-table-wrap operational statistics-table-wrap ${dense ? "dense" : ""}`} data-testid="connections-scroll">
    <table className="connection-table statistics-table">
      <thead><tr><th>状态</th><th>设备</th><th>目标</th><th>协议</th><th>命中规则</th><th>策略链路</th><th className="numeric">上传</th><th className="numeric">下载</th><th className="numeric">总流量</th><th>连接时间</th></tr></thead>
      <tbody>{connections.length ? connections.map(connection => {
        const protocol = connectionProtocol(connection);
        const active = connection.status === "active";
        return <tr key={connection.id} className={active ? "is-moving" : "is-ended"} onClick={() => onSelect?.(connection)} onContextMenu={event => { event.preventDefault(); onContext?.(event, connection); }}>
          <td><span className={`connection-status ${active ? "active" : "ended"}`}><i />{active ? "活跃" : "已结束"}</span></td>
          <td><span className="connection-device"><span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></span></td>
          <td><strong>{connection.host || connection.destinationIP}</strong><small>{connection.destinationIP}:{connection.destinationPort}</small></td>
          <td><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></td>
          <td>{connection.rule}</td>
          <td><div className="chain-text">{connection.chain.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div></td>
          <td className="numeric up">{bytes(connection.upload)}</td>
          <td className="numeric down">{bytes(connection.download)}</td>
          <td className="numeric cumulative">{bytes((connection.upload || 0) + (connection.download || 0))}</td>
          <td><strong>{connectionTime(connection.startedAt)}</strong><small>{active ? connectionDuration(connection.durationSeconds) : `结束 ${connectionTime(connection.endedAt)}`}</small></td>
        </tr>;
      }) : <tr className="connection-table-empty"><td colSpan="10">当前筛选条件下没有连接记录</td></tr>}</tbody>
    </table>
  </div>;
}

function ConnectionMobileList({ connections, onSelect, onContext }) {
  return <div className="connection-mobile-list" data-testid="connections-mobile-list">
    {connections.length ? connections.map(connection => {
      const protocol = connectionProtocol(connection);
      const active = connection.status === "active";
      return <article className={`connection-mobile-card ${active ? "is-active" : "is-ended"}`} key={connection.id} onClick={() => onSelect?.(connection)}>
        <header>
          <span className={`connection-status ${active ? "active" : "ended"}`}><i />{active ? "活跃" : "已结束"}</span>
          <span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span>
          <button type="button" aria-label={`打开 ${connection.host || connection.destinationIP} 的连接操作`} onClick={event => { event.stopPropagation(); const box = event.currentTarget.getBoundingClientRect(); onContext?.({ clientX: box.right, clientY: box.bottom, preventDefault() {} }, connection); }}><DotsThreeVertical weight="bold" /></button>
        </header>
        <div className="connection-mobile-target"><strong>{connection.host || connection.destinationIP}</strong><span>{connection.destinationIP}:{connection.destinationPort}</span></div>
        <div className="connection-mobile-source"><Desktop /><span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></div>
        <div className="connection-mobile-chain">{connection.chain.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div>
        <footer><span><small>总流量</small><strong>{bytes((connection.upload || 0) + (connection.download || 0))}</strong></span><span><small>上传 / 下载</small><strong>{bytes(connection.upload)} / {bytes(connection.download)}</strong></span><span><small>{active ? "持续时间" : "结束时间"}</small><strong>{active ? connectionDuration(connection.durationSeconds) : connectionTime(connection.endedAt)}</strong></span></footer>
      </article>;
    }) : <div className="connection-mobile-empty">当前筛选条件下没有连接记录</div>}
  </div>;
}

function ConnectionContextMenu({ state, canManage, onClose, onInspect, onDevice, onTerminate, onAddRule }) {
  if (!state) return null;
  const connection = state.connection;
  return <div className="connection-context-menu" style={{ left: state.x, top: state.y }} onClick={event => event.stopPropagation()} onContextMenu={event => event.preventDefault()}>
    <div className="context-target"><strong>{connection.host || connection.destinationIP}</strong><span>{connection.device} · {bytes((connection.upload || 0) + (connection.download || 0))}</span></div>
    <button onClick={() => { onInspect(connection); onClose(); }}><ListMagnifyingGlass />连接详情</button>
    <button onClick={() => { onDevice({ name: connection.device, ip: connection.sourceIP }); onClose(); }}><Desktop />设备流量历史</button>
    {canManage && <><div className="context-divider"/><button onClick={() => { onAddRule(connection); onClose(); }}><Plus />为目标增加规则</button>{connection.status !== "ended" && <button className="danger" onClick={() => { onTerminate(connection.id); onClose(); }}><Power />终止连接</button>}</>}
  </div>;
}

function ConnectionInspector({ connection, onClose, onDevice }) {
  if (!connection) return null;
  const protocol = connectionProtocol(connection);
  const total = (connection.upload || 0) + (connection.download || 0);
  return <div className="connection-inspector-layer" onMouseDown={onClose}>
    <aside className="connection-inspector" onMouseDown={event => event.stopPropagation()}>
      <div className="inspector-heading"><div><span>{connection.status === "ended" ? "历史连接" : "连接详情"}</span><h2>{connection.host || connection.destinationIP}</h2></div><button onClick={onClose}><X /></button></div>
      <div className="inspector-summary"><div><span>累计流量</span><strong>{bytes(total)}</strong></div><div><span>{connection.status === "ended" ? "连接时长" : "当前速率"}</span><strong>{connection.status === "ended" ? connectionDuration(connection.durationSeconds) : rate((connection.upRate || 0) + (connection.downRate || 0))}</strong></div></div>
      <dl className="connection-facts">
        <div><dt>来源设备</dt><dd>{connection.device}<small>{connection.sourceIP}</small></dd></div>
        <div><dt>目标地址</dt><dd>{connection.host || "IP 连接"}<small>{connection.destinationIP}:{connection.destinationPort}</small></dd></div>
        <div><dt>协议</dt><dd><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></dd></div>
        <div><dt>持续时间</dt><dd>{connection.duration || connectionDuration(connection.durationSeconds)}</dd></div>
        {connection.startedAt && <div><dt>开始时间</dt><dd>{connectionTime(connection.startedAt)}</dd></div>}
        {connection.startedAt && <div><dt>结束时间</dt><dd>{connection.endedAt ? connectionTime(connection.endedAt) : "仍在活动"}</dd></div>}
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

export function Dashboard({ data, strategies, onDevice, onNavigate, canManage }) {
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
        <div className="panel-heading"><h2>当前活跃连接</h2><button className="text-button" onClick={() => onNavigate("connections")}>查看连接统计</button></div>
        <ConnectionTable connections={data.connections.slice(0, 6)} onDevice={onDevice} dense />
      </section>
    </div>
  );
}
