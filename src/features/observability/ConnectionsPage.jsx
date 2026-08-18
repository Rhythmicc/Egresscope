import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  CirclesFour,
  ClockCounterClockwise,
  Desktop,
  DotsThreeVertical,
  ListMagnifyingGlass,
  MagnifyingGlass,
  Pause,
  Plus,
  Power,
  Pulse,
  Rows,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { connectionExitNode } from "../../lib/connections";
import { bytes, connectionDuration, connectionTime, rate } from "../../lib/formatters";

const DEMO_MODE = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === "true";

const connectionProtocol = (connection) => {
  const network = String(connection.network || "tcp").toUpperCase();
  if (network === "UDP" && Number(connection.destinationPort) === 443) return "QUIC";
  if (network === "TCP" && Number(connection.destinationPort) === 443) return "HTTPS";
  return network;
};

function RuleMatch({ connection, detailed = false }) {
  const source = connection.ruleSourceLabel || "规则";
  const raw = [connection.ruleType, connection.rulePayload].filter(Boolean).join(" · ");
  return <span className={`rule-match rule-source-${connection.ruleSource || "legacy"}`} title={raw || connection.rule || ""}>
    <strong>{connection.rule || "未识别规则"}</strong>
    <small>{source}{detailed && raw ? ` · ${raw}` : ""}</small>
  </span>;
}

function ConnectionTable({ connections, onDevice, onSelect, onContext, dense = false, operational = false }) {
  return (
    <div className={`connection-table-wrap ${dense ? "dense" : ""} ${operational ? "operational" : ""}`} data-testid={operational ? "connections-scroll" : undefined}>
      <table className="connection-table">
        <thead><tr><th>设备</th><th>目标</th><th>协议</th><th>命中规则</th><th>出口节点</th><th className="numeric">上行速率</th><th className="numeric">下行速率</th><th className="numeric">累计流量</th><th>持续时间</th></tr></thead>
        <tbody>
          {connections.map((connection) => { const protocol = connectionProtocol(connection); const moving = connection.upRate + connection.downRate > 0; return (
            <tr key={connection.id} className={moving ? "is-moving" : "is-idle"} onClick={() => onSelect ? onSelect(connection) : onDevice?.({ name: connection.device, ip: connection.sourceIP })} onContextMenu={(event) => { if (!onContext) return; event.preventDefault(); onContext(event, connection); }}>
              <td><span className="connection-device"><i /> <span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></span></td>
              <td><strong>{connection.host || connection.destinationIP}</strong><small>{connection.destinationIP}:{connection.destinationPort}</small></td>
              <td><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></td>
              <td><RuleMatch connection={connection} /></td>
              <td><span className="connection-exit-node" title={connectionExitNode(connection)}>{connectionExitNode(connection)}</span></td>
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

function ConnectionStatisticsTable({ connections, onSelect, onContext, dense = false, showStatus = true }) {
  return <div className={`connection-table-wrap operational statistics-table-wrap ${dense ? "dense" : ""}`} data-testid="connections-scroll">
    <table className={`connection-table statistics-table ${showStatus ? "has-status" : "without-status"}`}>
      <thead><tr>{showStatus && <th className="column-status">状态</th>}<th className="column-device">设备</th><th className="column-target">目标</th><th className="column-protocol">协议</th><th className="column-rule">命中规则</th><th className="column-exit">出口节点</th><th className="numeric column-upload">上传</th><th className="numeric column-download">下载</th><th className="numeric column-total">总流量</th><th className="column-time">连接时间</th></tr></thead>
      <tbody>{connections.length ? connections.map(connection => {
        const protocol = connectionProtocol(connection);
        const active = connection.status === "active";
        return <tr key={connection.id} className={active ? "is-moving" : "is-ended"} onClick={() => onSelect?.(connection)} onContextMenu={event => { event.preventDefault(); onContext?.(event, connection); }}>
          {showStatus && <td className="column-status"><span className={`connection-status ${active ? "active" : "ended"}`}><i />{active ? "活跃" : "已结束"}</span></td>}
          <td className="column-device"><span className="connection-device"><span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></span></td>
          <td className="column-target"><strong>{connection.host || connection.destinationIP}</strong><small>{connection.destinationIP}:{connection.destinationPort}</small></td>
          <td className="column-protocol"><span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span></td>
          <td className="column-rule"><RuleMatch connection={connection} /></td>
          <td className="column-exit"><span className="connection-exit-node" title={connectionExitNode(connection)}>{connectionExitNode(connection)}</span></td>
          <td className="numeric up column-upload">{bytes(connection.upload)}</td>
          <td className="numeric down column-download">{bytes(connection.download)}</td>
          <td className="numeric cumulative column-total">{bytes((connection.upload || 0) + (connection.download || 0))}</td>
          <td className="column-time"><strong>{connectionTime(connection.startedAt)}</strong><small>{active ? connectionDuration(connection.durationSeconds) : `结束 ${connectionTime(connection.endedAt)}`}</small></td>
        </tr>;
      }) : <tr className="connection-table-empty"><td colSpan={showStatus ? 10 : 9}>当前筛选条件下没有连接记录</td></tr>}</tbody>
    </table>
  </div>;
}

function ConnectionMobileList({ connections, onSelect, onContext, showStatus = true }) {
  return <div className="connection-mobile-list" data-testid="connections-mobile-list">
    {connections.length ? connections.map(connection => {
      const protocol = connectionProtocol(connection);
        const active = connection.status === "active";
        return <article className={`connection-mobile-card ${active ? "is-active" : "is-ended"}`} key={connection.id} onClick={() => onSelect?.(connection)}>
        <header>
          {showStatus && <span className={`connection-status ${active ? "active" : "ended"}`}><i />{active ? "活跃" : "已结束"}</span>}
          <span className={`protocol protocol-${protocol.toLowerCase()}`}>{protocol}</span>
          <button type="button" aria-label={`打开 ${connection.host || connection.destinationIP} 的连接操作`} onClick={event => { event.stopPropagation(); const box = event.currentTarget.getBoundingClientRect(); onContext?.({ clientX: box.right, clientY: box.bottom, preventDefault() {} }, connection); }}><DotsThreeVertical weight="bold" /></button>
        </header>
        <div className="connection-mobile-target"><strong>{connection.host || connection.destinationIP}</strong><span>{connection.destinationIP}:{connection.destinationPort}</span></div>
        <div className="connection-mobile-source"><Desktop /><span><strong>{connection.device}</strong><small>{connection.sourceIP}</small></span></div>
        <div className="connection-mobile-rule"><span>命中规则</span><RuleMatch connection={connection} /></div>
        <div className="connection-mobile-exit"><small>出口节点</small><strong title={connectionExitNode(connection)}>{connectionExitNode(connection)}</strong></div>
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
        <div className="wide"><dt>命中规则</dt><dd><RuleMatch connection={connection} detailed /></dd></div>
        <div className="wide"><dt>完整策略链路</dt><dd><div className="inspector-chain">{connection.chain.map((item,index)=><span key={`${item}-${index}`}>{item}</span>)}</div></dd></div>
      </dl>
      <button className="primary-button inspector-device-button" onClick={() => onDevice({ name: connection.device, ip: connection.sourceIP })}>查看该设备的目标与历史流量</button>
    </aside>
  </div>;
}

export function QuickRuleModal({ editor, setEditor, onSave, contextLabel = "实时连接" }) {
  if (!editor) return null;
  const prefix = editor.matchType === "IP-CIDR" ? `${editor.value}${editor.value.includes(":") ? "/128" : "/32"}` : editor.value;
  const content = `${editor.matchType},${prefix},${editor.policy}${editor.matchType === "IP-CIDR" ? ",no-resolve" : ""}`;
  return <div className="modal-backdrop" onMouseDown={() => !editor.busy && setEditor(null)}><form className="user-modal quick-rule-modal" onMouseDown={event => event.stopPropagation()} onSubmit={event => { event.preventDefault(); onSave({ ...editor, content }); }}>
    <div className="modal-heading"><div><span className="eyebrow">{contextLabel}</span><h3>为目标增加规则</h3></div><button type="button" disabled={editor.busy} onClick={() => setEditor(null)}><X /></button></div>
    <div className="quick-rule-grid"><label>匹配方式<select value={editor.matchType} onChange={event => setEditor({ ...editor, matchType: event.target.value })}><option value="DOMAIN">精确域名</option><option value="DOMAIN-SUFFIX">域名后缀</option><option value="IP-CIDR">目标 IP</option></select></label><label>目标<input required value={editor.value} onChange={event => setEditor({ ...editor, value: event.target.value })}/></label></div>
    <label>执行策略<select value={editor.policy} onChange={event => setEditor({ ...editor, policy: event.target.value })}>{editor.policies.map(policy => <option key={policy}>{policy}</option>)}</select></label>
    <div className="rule-preview"><span>将写入</span><code>{content}</code></div>
    {editor.connection.status === "active" && !editor.connection.grouped && <label className="quick-rule-reconnect"><input type="checkbox" checked={editor.terminateCurrent ?? true} onChange={event => setEditor({ ...editor, terminateCurrent:event.target.checked })}/><strong>应用后终止当前连接，让新规则立即接管重连</strong></label>}
    {editor.error && <div className="login-error"><WarningCircle />{editor.error}</div>}
    <button className="primary-button modal-submit" disabled={editor.busy || !editor.policy}>{editor.busy ? "正在应用…" : "保存并应用"}</button>
  </form></div>;
}

const demoConnectionStatistics = (data, status) => {
  const now = Math.floor(Date.now() / 1000);
  const active = (data.connections || []).slice(0, 18).map((connection, index) => ({ ...connection, status: "active", startedAt: now - 240 - index * 93, lastSeenAt: now, endedAt: null, durationSeconds: 240 + index * 93 }));
  const history = (data.connections || []).slice(8, 38).map((connection, index) => ({ ...connection, id: `history-${connection.id}`, status: "ended", startedAt: now - 3600 - index * 420, lastSeenAt: now - 480 - index * 180, endedAt: now - 480 - index * 180, durationSeconds: 310 + index * 37, upRate: 0, downRate: 0 }));
  const all = status === "active" ? active : status === "history" ? history : [...active, ...history];
  const everySession = [...active, ...history];
  return { range: "24h", status, retentionDays: 30, summary: { active: active.length, history: history.length, total: everySession.length, devices: new Set(everySession.map(item => item.sourceIP)).size, traffic: everySession.reduce((sum, item) => sum + item.upload + item.download, 0), matched: all.length }, sessions: all };
};

const emptyConnectionStatistics = (range = "24h", status = "active") => ({
  range,
  status,
  retentionDays: 30,
  summary: { active: 0, history: 0, total: 0, devices: 0, traffic: 0, matched: 0 },
  sessions: [],
});

export function ConnectionsPage({ data, onDevice, canManage }) {
  const [query, setQuery] = useState("");
  const [deviceFilter, setDeviceFilter] = useState("");
  const [networkFilter, setNetworkFilter] = useState("");
  const [mode, setMode] = useState("active");
  const [range, setRange] = useState("24h");
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState([]);
  const [compact, setCompact] = useState(true);
  const [message, setMessage] = useState("");
  const [contextMenu, setContextMenu] = useState(null);
  const [inspected, setInspected] = useState(null);
  const [quickRule, setQuickRule] = useState(null);
  const [statistics, setStatistics] = useState(() => emptyConnectionStatistics());
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    let mounted = true;
    let timer;
    const load = async () => {
      if (paused) return;
      setLoading(true);
      try { const result = await api.connectionStatistics(range, mode); if (mounted) setStatistics(result); }
      catch (error) { if (DEMO_MODE && mounted) setStatistics(demoConnectionStatistics(data, mode)); else if (mounted) setMessage(error.message); }
      finally { if (mounted) setLoading(false); }
    };
    load();
    if (!paused) timer = setInterval(load, mode === "active" ? 5000 : 15000);
    return () => { mounted = false; clearInterval(timer); };
  }, [range, mode, paused, refreshKey]);
  const source = paused ? snapshot : statistics.sessions || [];
  const devices = [...new Map((statistics.sessions || []).map(connection => [connection.sourceIP, { ip: connection.sourceIP, name: connection.device }])).values()].sort((a,b) => a.name.localeCompare(b.name));
  const filtered = source.filter((c) => (!deviceFilter || c.sourceIP === deviceFilter) && (!networkFilter || connectionProtocol(c) === networkFilter) && `${c.device} ${c.sourceIP} ${c.host} ${c.destinationIP} ${c.rule} ${c.chain.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const togglePause = () => { if (!paused) setSnapshot(statistics.sessions || []); setPaused(current => !current); };
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
    try { await api.closeConnection(id); setMessage("连接已终止；记录将保留在历史连接中。"); setRefreshKey(value => value + 1); }
    catch (error) { setMessage(error.message); }
  };
  const openQuickRule = async (connection) => {
    const host = connection.host && !/^[\d.:]+$/.test(connection.host) ? connection.host : "";
    const initial = { connection, matchType: host ? "DOMAIN" : "IP-CIDR", value: host || connection.destinationIP, policy: "", policies: [], terminateCurrent:connection.status === "active", busy: true, error: "" };
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
      await api.createCustomRule({ content: editor.content, placement: "before", note: `来自连接统计：${editor.connection.device}` });
      await api.applyRules();
      if (editor.terminateCurrent && editor.connection.status === "active") {
        try { await api.closeConnection(editor.connection.id); setMessage(`规则已应用，当前连接已终止并等待重连：${editor.content}`); }
        catch { setMessage(`规则已应用，但当前连接已结束或未能终止：${editor.content}`); }
      } else setMessage(`规则已应用：${editor.content}`);
      setQuickRule(null);
    } catch (error) { setQuickRule({ ...editor, busy: false, error: error.message }); }
  };
  const closeAll = async () => {
    if (!window.confirm("确定终止当前全部连接？应用可能会自动重连。")) return;
    try { await api.closeAllConnections(); setMessage("全部连接已终止，并将转入历史记录。"); setRefreshKey(value => value + 1); }
    catch (error) { setMessage(error.message); }
  };
  return (
    <div className="page-content list-page connections-page">
      <section className="panel full-height-panel connections-workspace">
        <div className="connection-stat-summary">
          <div><span>当前活跃</span><strong>{statistics.summary?.active || 0}</strong></div>
          <div><span>历史连接</span><strong>{statistics.summary?.history || 0}</strong></div>
          <div><span>累计流量</span><strong>{bytes(statistics.summary?.traffic || 0)}</strong></div>
          <div><span>涉及设备</span><strong>{statistics.summary?.devices || 0}</strong></div>
        </div>
        <div className="connection-modebar"><div><button className={mode === "active" ? "active" : ""} onClick={() => setMode("active")}>活跃连接</button><button className={mode === "history" ? "active" : ""} onClick={() => setMode("history")}>历史记录</button><button className={mode === "all" ? "active" : ""} onClick={() => setMode("all")}>全部连接</button></div><span><ClockCounterClockwise />数据库保留 {statistics.retentionDays || 30} 天</span></div>
        <div className="list-toolbar">
          <select className="connection-range" value={range} onChange={event => setRange(event.target.value)}><option value="1h">最近 1 小时</option><option value="6h">最近 6 小时</option><option value="24h">最近 24 小时</option><option value="7d">最近 7 天</option><option value="30d">最近 30 天</option></select>
          <select value={deviceFilter} onChange={event => setDeviceFilter(event.target.value)}><option value="">所有设备</option>{devices.map(device => <option key={device.ip} value={device.ip}>{device.name} · {device.ip}</option>)}</select>
          <select value={networkFilter} onChange={event => setNetworkFilter(event.target.value)}><option value="">所有协议</option><option value="HTTPS">HTTPS</option><option value="QUIC">QUIC</option><option value="TCP">TCP</option><option value="UDP">UDP</option></select>
          <div className="search-box"><MagnifyingGlass /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索设备、目标、规则或出口节点" />{query && <button onClick={() => setQuery("")}><X /></button>}</div>
          <button className={`toolbar-icon ${paused ? "active" : ""}`} aria-label={paused ? "恢复自动刷新" : "暂停列表"} title={paused ? "恢复自动刷新" : "暂停列表"} onClick={togglePause}>{paused ? <Pulse weight="fill" /> : <Pause weight="fill" />}</button>
          <button className="toolbar-icon" aria-label={compact ? "切换舒适密度" : "切换紧凑密度"} title={compact ? "切换舒适密度" : "切换紧凑密度"} onClick={() => setCompact(current => !current)}>{compact ? <Rows /> : <CirclesFour />}</button>
          {canManage && mode !== "history" && <button className="danger-button" onClick={closeAll}>终止全部</button>}
        </div>
        {message && <div className="inline-message">{message}</div>}
        <ConnectionStatisticsTable connections={filtered} onSelect={setInspected} onContext={openContextMenu} dense={compact} showStatus={mode !== "active"} />
        <ConnectionMobileList connections={filtered} onSelect={setInspected} onContext={openContextMenu} showStatus={mode !== "active"} />
        <div className="list-summary"><span className={paused ? "paused-dot" : "live-dot"} />{paused ? "已暂停" : loading ? "更新中" : mode === "active" ? "实时更新" : "历史记录"}<b>{filtered.length} / {statistics.summary?.matched || 0} 条连接</b>{mode === "active" && <><span>↑ {rate(data.totals.upRate)}</span><span>↓ {rate(data.totals.downRate)}</span></>}<small>Asia/Shanghai</small></div>
      </section>
      <ConnectionContextMenu state={contextMenu} canManage={canManage} onClose={() => setContextMenu(null)} onInspect={setInspected} onDevice={onDevice} onTerminate={closeOne} onAddRule={openQuickRule} />
      <ConnectionInspector connection={inspected} onClose={() => setInspected(null)} onDevice={device => { setInspected(null); onDevice(device); }} />
      <QuickRuleModal editor={quickRule} setEditor={setQuickRule} onSave={saveQuickRule} />
    </div>
  );
}
