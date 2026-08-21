import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowClockwise,
  ArrowsDownUp,
  CaretDown,
  CheckCircle,
  CloudArrowDown,
  Copy,
  DotsThreeVertical,
  DownloadSimple,
  FileCode,
  Funnel,
  HardDrives,
  LinkSimple,
  Lightning,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  ShieldCheck,
  Stack,
  Trash,
  WarningCircle,
  WifiHigh,
  X,
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
import { canOpenPage, PAGE_TITLES, pageDefinition } from "./app/page-map";
import { PageRenderer } from "./app/PageRenderer";
import { LoginScreen, ServiceUnavailable } from "./components/AuthScreens";
import { Sidebar, Topbar } from "./components/AppShell";
import { demoDashboard, demoDevice, demoStrategies } from "./demo-data";
import { ConnectionsPage } from "./features/observability/ConnectionsPage";
import { Dashboard } from "./features/observability/DashboardPage";
import { DeviceFlow } from "./features/observability/DeviceAnalysisPage";
import { AuditPage } from "./features/observability/TrafficAnalysisPage";
import { UsersPage } from "./features/users/UsersPage";
import { ChangePasswordDialog } from "./features/users/PasswordDialog";
import { bytes, connectionDuration, connectionTime, rate } from "./lib/formatters";

const DEMO_MODE = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === "true";

function StrategiesPage({ strategies, onChanged, canManage }) {
  const [expanded, setExpanded] = useState(() => {
    const section = new URLSearchParams(location.search).get("section");
    if (section === "secondary") {
      const first = (strategies.secondary || []).find(group => group.selectable);
      return first ? new Set([first.id]) : new Set();
    }
    return new Set((strategies.primary || []).slice(0, 1).map(group => group.id));
  });
  const [secondaryExpanded, setSecondaryExpanded] = useState(() => new URLSearchParams(location.search).get("section") === "secondary");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const [reconnect, setReconnect] = useState(true);
  const [testing, setTesting] = useState(false);
  const [pending, setPending] = useState({});
  const runTestDelay = async () => {
    setTesting(true);
    setMessage("正在重新测速…");
    try {
      const result = await api.testStrategyDelays();
      setMessage(`重新测速完成：${result.updated ?? result.tested ?? 0} 个策略组已更新（${result.elapsedMs} ms）`);
      await onChanged(result.strategies);
    } catch (error) { setMessage(error.message); }
    finally { setTesting(false); }
  };
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
    // 只有父组当前出口对应的子组（如 美国 → 美国智能）里选中的节点才是真正的当前出口；
    // 其余子组（最佳/均衡）各自的 now 只是组内状态，不代表流量实际走的节点，不标 selected。
    const activeChildId = group.now;
    const unique = new Map();
    group.children?.forEach(child => {
      const isActive = child.id === activeChildId;
      child.members?.forEach(member => {
        const existing = unique.get(member.id);
        const selected = isActive && member.selected;
        unique.set(member.id, existing ? { ...existing, ...member, selected: existing.selected || selected } : { ...member, selected });
      });
    });
    return [...unique.values()];
  };
  const toggle = (id) => setExpanded(current => {
    if (current.has(id)) return new Set();
    return new Set([id]);
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
      <div className="proxy-workbench-head"><h2>分流策略</h2><div className="proxy-workbench-actions"><label className="proxy-search"><MagnifyingGlass /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索策略或节点" /></label>{canManage && <button type="button" className="retest-button" disabled={testing} onClick={runTestDelay}><ArrowClockwise className={testing ? "spinning" : ""} />{testing ? "测速中…" : "重新测速"}</button>}{canManage && <label className="reconnect-toggle"><input type="checkbox" checked={reconnect} onChange={event => setReconnect(event.target.checked)} /><span><strong>切换后重连</strong></span></label>}</div></div>
      {message && <div className="inline-message strategy-message">{message}</div>}
      <div className="proxy-groups">{strategies.primary.map(strategySection)}
      <button className="collapsed-groups proxy-secondary-toggle" onClick={() => setSecondaryExpanded(!secondaryExpanded)}><span><Stack />其他规则策略</span><small>{strategies.secondaryCount} 个</small><CaretDown className={secondaryExpanded ? "rotated" : ""}/></button>
      {secondaryExpanded && <div className="secondary-grid">{strategies.secondary.filter(group => !query || `${group.name} ${group.now}`.toLowerCase().includes(query.toLowerCase())).map(group => group.selectable ? (
        <section className={`secondary-group-card ${expanded.has(group.id) ? "is-open" : ""}`} key={group.id}>
          <button className="secondary-group-head" type="button" onClick={() => toggle(group.id)}>
            <span className="secondary-group-name"><b>{group.name}</b><em>{group.typeLabel}</em></span>
            <span className="secondary-group-state"><small>{group.health?.available ?? group.members?.length ?? 0}/{group.health?.total ?? group.members?.length ?? 0} 可用</small><strong>{pending[group.id] ? `正在切换至 ${pending[group.id]}` : group.now}</strong>{delayChip(group)}<CaretDown className={expanded.has(group.id) ? "rotated" : ""} /></span>
          </button>
          {(expanded.has(group.id) || Boolean(query)) && <div className="proxy-member-grid">{group.members.filter(member => !query || `${member.name} ${group.name}`.toLowerCase().includes(query.toLowerCase())).map(member => memberCard(group, member))}</div>}
        </section>
      ) : (
        <div className="secondary-group" key={group.id}><span>{group.name}<em>{group.modeLabel}</em></span><strong>{group.now}</strong><small>{group.health?.available ?? 0}/{group.health?.total ?? 0} 可用</small>{delayChip(group)}</div>
      ))}</div>}</div>
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
  const [github, setGithub] = useState(null);
  const [githubEditor, setGithubEditor] = useState(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const load = async () => {
    try { setWorkspace(await api.ruleWorkspace()); }
    catch (error) { if (DEMO_MODE) setWorkspace(demoRuleWorkspace); else setMessage(error.message); }
  };
  useEffect(() => { load(); api.githubSync().then(setGithub).catch(() => {}); }, []);
  const openGithubEditor = () => setGithubEditor({ repo: github?.repo || "", branch: github?.branch || "", path: github?.path || "", token: "", tokenConfigured: Boolean(github?.tokenConfigured) });
  const saveGithubConfig = async (event) => {
    event.preventDefault();
    setSyncBusy(true); setMessage("");
    try {
      const result = await api.saveGithubSync({ repo: githubEditor.repo, branch: githubEditor.branch, path: githubEditor.path, token: githubEditor.token || undefined });
      setGithub(result);
      setGithubEditor(null);
      setMessage("GitHub 同步配置已保存。");
    } catch (error) { setMessage(error.message); }
    finally { setSyncBusy(false); }
  };
  const runGithubSync = async (action, confirmText) => {
    const prompt = confirmText || (action === "push" ? "推送会用本地自定义规则覆盖 GitHub 文件，继续吗？" : "");
    if (prompt && !window.confirm(prompt)) return;
    setSyncBusy(true); setMessage("");
    try {
      const result = action === "push" ? await api.githubSyncPush() : await api.githubSyncPull();
      await load();
      setGithub(await api.githubSync());
      setGithubEditor(null);
      setMessage(action === "push"
        ? `已推送到 GitHub：${result.branch} @ ${result.commitSha || "—"}，共 ${result.count} 条规则。`
        : `已从 GitHub 拉取 ${result.customRules} 条规则，点击「应用更改」后生效。`);
    } catch (error) { setMessage(error.message); }
    finally { setSyncBusy(false); }
  };
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
    <div className="rules-hero"><h2>规则管理</h2><div className="rules-actions">{canManage && <button className="filter-button" disabled={busy} onClick={() => setSetEditor({ ...emptyRuleSet, policy: workspace?.availablePolicies?.[0] || "" })}>添加规则集</button>}{canManage && <button className="filter-button" disabled={busy} onClick={() => setCustomEditor({ content: "DOMAIN-SUFFIX,example.com,DIRECT", placement: "before", note: "", enabled: true })}>添加单条规则</button>}{canManage && <button className="filter-button" disabled={busy || !workspace?.appliedRevision} onClick={() => run(() => Promise.all((workspace?.ruleSets || []).filter(item => item.enabled).map(item => api.refreshRuleSet(item.id))), "所有已启用规则集均已刷新。")}>刷新规则源</button>}{canManage && <button className="filter-button" disabled={syncBusy} onClick={openGithubEditor}>GitHub 同步</button>}{canManage && <button className="primary-button" disabled={busy || !workspace?.dirty} onClick={() => run(api.applyRules, "规则已校验并热重载到网关。")}>{busy ? "处理中…" : workspace?.dirty ? "应用更改" : "已应用"}</button>}</div></div>
    {message && <div className="inline-message">{message}</div>}
    <div className="rule-stat-grid"><div><span>规则集</span><strong>{workspace?.counts?.ruleSets ?? "—"}</strong></div><div><span>自定义规则</span><strong>{workspace?.counts?.customRules ?? "—"}</strong></div><div><span>工作区版本</span><strong>r{workspace?.revision ?? "—"}</strong></div><div><span>安全兜底</span><strong>{workspace?.fallbackRules?.at(-1)?.policy || "—"}</strong></div></div>
    <section className="panel rule-set-panel"><div className="rule-toolbar"><h3>有序规则集</h3><label className="search-box"><MagnifyingGlass /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索名称、来源或目标策略" />{query && <button onClick={() => setQuery("")}><X /></button>}</label></div><div className="rule-set-head"><span>顺序 / 状态</span><span>规则集</span><span>目标策略</span><span>更新周期</span><span>操作</span></div><div className="rule-set-list">{sets.map((item, visibleIndex) => { const index = workspace.ruleSets.findIndex(row => row.id === item.id); return <div className={`rule-set-row ${!item.enabled ? "disabled" : ""}`} key={item.id}><span className="rule-order"><b>{String(index + 1).padStart(2,"0")}</b><label className="rule-switch"><input type="checkbox" disabled={!canManage || busy} checked={item.enabled} onChange={event => run(() => api.updateRuleSet(item.id, { enabled: event.target.checked }), event.target.checked ? "规则集已启用，应用后生效。" : "规则集已停用，应用后生效。")} /><i /></label></span><span className="rule-set-name"><strong>{item.name}</strong><small>{sourceHost(item.url)} · {item.behavior}/{item.format}</small></span><span><b className="policy-chip">{item.policy}</b></span><span className="rule-interval">{Math.round(item.interval / 3600)} 小时</span><span className="rule-row-actions">{canManage && <><button disabled={busy || index === 0 || query} title="上移" onClick={() => run(() => api.moveRuleSet(item.id,"up"), "顺序已调整，应用后生效。")}>↑</button><button disabled={busy || index === workspace.ruleSets.length - 1 || query} title="下移" onClick={() => run(() => api.moveRuleSet(item.id,"down"), "顺序已调整，应用后生效。")}>↓</button><button onClick={() => setSetEditor({ ...item })}>编辑</button><button className="danger-link" onClick={() => confirm(`删除规则集「${item.name}」？`) && run(() => api.deleteRuleSet(item.id), "规则集已删除，应用后生效。")}>删除</button></>}</span></div>; })}</div></section>
    <section className="panel custom-rules-panel"><div className="panel-heading"><h2>自定义覆盖规则</h2></div>{workspace?.customRules?.length ? <div className="custom-rule-list">{workspace.customRules.map(rule => <div className={!rule.enabled ? "disabled" : ""} key={rule.id}><label className="rule-switch"><input type="checkbox" disabled={!canManage} checked={rule.enabled} onChange={event => run(() => api.updateCustomRule(rule.id,{ enabled:event.target.checked }), "规则状态已更新。")}/><i /></label><span className="rule-placement">{rule.placement === "after" ? "后置" : "前置"}</span><code>{rule.content}</code><span className="policy-chip">{rule.policy}</span>{canManage && <span className="rule-row-actions"><button onClick={() => setCustomEditor({ ...rule })}>编辑</button><button className="danger-link" onClick={() => confirm("删除这条自定义规则？") && run(() => api.deleteCustomRule(rule.id), "自定义规则已删除。")}>删除</button></span>}</div>)}</div> : <div className="empty-rules">还没有自定义规则</div>}</section>
    {setEditor && <div className="modal-backdrop" onMouseDown={() => setSetEditor(null)}><form className="user-modal rule-modal" role="dialog" aria-modal="true" aria-labelledby="rule-set-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveSet}><div className="modal-heading"><div><span className="eyebrow">规则集</span><h3 id="rule-set-editor-title">{setEditor.id ? "编辑规则集" : "添加规则集"}</h3></div><button type="button" aria-label="关闭规则集编辑器" onClick={() => setSetEditor(null)}><X /></button></div><label>名称<input required autoFocus value={setEditor.name} onChange={event => setSetEditor({...setEditor,name:event.target.value})}/></label><label>远程地址<input required type="url" value={setEditor.url} onChange={event => setSetEditor({...setEditor,url:event.target.value})}/></label><label>目标策略<select value={setEditor.policy} onChange={event => setSetEditor({...setEditor,policy:event.target.value})}>{workspace.availablePolicies.map(policy => <option key={policy} value={policy}>{policy}</option>)}</select></label><div className="modal-fields"><label>更新周期（秒）<input type="number" min="300" value={setEditor.interval} onChange={event => setSetEditor({...setEditor,interval:Number(event.target.value)})}/></label><label>内容格式<select value={setEditor.format} onChange={event => setSetEditor({...setEditor,format:event.target.value})}><option value="text">text</option><option value="yaml">yaml</option><option value="mrs">mrs</option></select></label></div><button className="primary-button modal-submit" disabled={busy}>保存到工作区</button></form></div>}
    {customEditor && <div className="modal-backdrop" onMouseDown={() => setCustomEditor(null)}><form className="user-modal rule-modal" role="dialog" aria-modal="true" aria-labelledby="custom-rule-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveCustom}><div className="modal-heading"><div><span className="eyebrow">请求匹配</span><h3 id="custom-rule-editor-title">{customEditor.id ? "编辑自定义规则" : "添加自定义规则"}</h3></div><button type="button" aria-label="关闭自定义规则编辑器" onClick={() => setCustomEditor(null)}><X /></button></div><label>规则内容<input required autoFocus value={customEditor.content} onChange={event => setCustomEditor({...customEditor,content:event.target.value})} placeholder="DOMAIN-SUFFIX,example.com,节点选择"/><small>使用 mihomo 规则语法；保存后会解析并在应用时校验策略引用。</small></label><label>位置<select value={customEditor.placement} onChange={event => setCustomEditor({...customEditor,placement:event.target.value})}><option value="before">规则集之前（高优先级）</option><option value="after">规则集之后（低优先级）</option></select></label><label>备注<input value={customEditor.note || ""} onChange={event => setCustomEditor({...customEditor,note:event.target.value})}/></label><button className="primary-button modal-submit" disabled={busy}>保存到工作区</button></form></div>}
    {githubEditor && <div className="modal-backdrop" onMouseDown={() => setGithubEditor(null)}><form className="user-modal rule-modal" role="dialog" aria-modal="true" aria-labelledby="github-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveGithubConfig}><div className="modal-heading"><div><span className="eyebrow">自定义规则</span><h3 id="github-editor-title">GitHub 同步</h3></div><button type="button" aria-label="关闭 GitHub 同步" onClick={() => setGithubEditor(null)}><X /></button></div><label>仓库<input autoFocus value={githubEditor.repo} onChange={event => setGithubEditor({...githubEditor,repo:event.target.value})} placeholder="例如 Rhythmicc/ACL4SSR" required/></label><label>分支<input value={githubEditor.branch} onChange={event => setGithubEditor({...githubEditor,branch:event.target.value})} placeholder="留空使用仓库默认分支"/></label><label>文件路径<input value={githubEditor.path} onChange={event => setGithubEditor({...githubEditor,path:event.target.value})} placeholder="例如 Clash/egresscope-custom-rules.json" required/></label><label>Personal Access Token<input type="password" autoComplete="new-password" value={githubEditor.token || ""} onChange={event => setGithubEditor({...githubEditor,token:event.target.value})} placeholder={githubEditor.tokenConfigured ? "已配置；留空表示保留" : "需要 repo 写权限的 Token"}/></label>{github?.lastError && <div className="subscription-error"><WarningCircle />{github.lastError}</div>}<div className="modal-actions-row"><button type="submit" className="primary-button modal-submit" disabled={syncBusy}>{syncBusy ? "处理中…" : "保存配置"}</button><button type="button" className="filter-button" disabled={syncBusy || !github?.tokenConfigured} onClick={() => runGithubSync("pull", "拉取会用 GitHub 上的规则替换本地自定义规则，继续吗？")}>从 GitHub 拉取</button><button type="button" className="filter-button" disabled={syncBusy || !github?.tokenConfigured} onClick={() => runGithubSync("push")}>推送到 GitHub</button></div>{github?.lastSyncAt ? <div className="github-sync-status">上次同步 {shanghaiTime(github.lastSyncAt)}</div> : <div className="github-sync-status">尚未同步</div>}</form></div>}
  </div>;
}

const shanghaiTime = (timestamp) => timestamp ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(timestamp * 1000)) : "尚无记录";
const shanghaiDateTime = (timestamp) => timestamp ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(timestamp * 1000)) : "—";
const runtimeDuration = (seconds = 0) => {
  const value = Math.max(0, Number(seconds) || 0);
  const days = Math.floor(value / 86400);
  const hours = Math.floor(value % 86400 / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  return `${days ? `${days} 天 ` : ""}${hours} 小时 ${minutes} 分钟`;
};

const DEMO_GATEWAY = {
  runtime: {
    startedAt: Date.parse("2026-08-10T05:30:23+08:00") / 1000, uptimeSeconds: 252557, online: true, version: "1.19.29",
    total: 13.24 * 1024 ** 3, activeExits: 4,
    access: [
      { id: "gateway", name: "透明网关", up: 1.24 * 1024 ** 3, down: 4.63 * 1024 ** 3, total: 5.87 * 1024 ** 3, currentUpRate: 3400, currentDownRate: 128000, peakUpRate: 12.5 * 1024 ** 2, peakDownRate: 31.7 * 1024 ** 2, devices: ["workstation", "compute-node", "storage-node"] },
      { id: "proxy", name: "显式代理", up: 1.61 * 1024 ** 3, down: 5.76 * 1024 ** 3, total: 7.37 * 1024 ** 3, currentUpRate: 1200, currentDownRate: 44000, peakUpRate: 9.8 * 1024 ** 2, peakDownRate: 24.1 * 1024 ** 2, devices: ["9462"] },
    ],
    exits: [
      { name: "DIRECT", up: 2.85 * 1024 ** 3, down: 9.54 * 1024 ** 3, total: 12.39 * 1024 ** 3, currentUpRate: 0, currentDownRate: 0, peakUpRate: 22.5 * 1024 ** 2, peakDownRate: 45.7 * 1024 ** 2, activeConnections: 8 },
      { name: "🇺🇸 奶昔-美国西雅图 04", up: 2.1 * 1024 ** 2, down: 5.6 * 1024 ** 2, total: 7.7 * 1024 ** 2, currentUpRate: 900, currentDownRate: 18200, peakUpRate: 840000, peakDownRate: 3200000, activeConnections: 4 },
      { name: "🇺🇸 奶昔-美国圣何塞 07", up: 2.8 * 1024 ** 2, down: 6.1 * 1024 ** 2, total: 8.9 * 1024 ** 2, currentUpRate: 540, currentDownRate: 11300, peakUpRate: 620000, peakDownRate: 2700000, activeConnections: 2 },
    ],
  },
  events: {
    total: 6, retentionDays: 90, events: [
      { id: 1, level: "info", category: "strategy", title: "策略已切换", message: "🇺🇸 美国最佳 现在指向 🇺🇸 奶昔-美国西雅图 04", createdAt: Date.parse("2026-08-13T03:07:16+08:00") / 1000 },
      { id: 2, level: "info", category: "gateway", title: "网关已连接", message: "mihomo 控制面和流量采集均已恢复。", createdAt: Date.parse("2026-08-13T02:47:10+08:00") / 1000 },
      { id: 3, level: "error", category: "mihomo", title: "节点连接失败", message: "proxy 🇺🇸 奶昔-美国洛杉矶 03: connection refused", createdAt: Date.parse("2026-08-13T02:43:39+08:00") / 1000 },
      { id: 4, level: "warning", category: "mihomo", title: "节点连接超时", message: "dial timeout while connecting to upstream proxy", createdAt: Date.parse("2026-08-13T02:42:18+08:00") / 1000 },
    ],
  },
};

function GatewayPage({ canManage }) {
  const [aliases, setAliases] = useState({});
  const [devices, setDevices] = useState([]);
  const [message, setMessage] = useState("");
  const [tab, setTab] = useState("runtime");
  const [runtime, setRuntime] = useState(null);
  const [events, setEvents] = useState({ events: [], total: 0, retentionDays: 90 });
  const [eventLevel, setEventLevel] = useState("all");
  const [eventQuery, setEventQuery] = useState("");
  const [openRows, setOpenRows] = useState(new Set(["access:gateway", "exit:DIRECT"]));
  const [kernel, setKernel] = useState(null);
  const [kernelVersion, setKernelVersion] = useState("");
  const [kernelBusy, setKernelBusy] = useState(false);
  const [geoip, setGeoip] = useState(null);
  const [regions, setRegions] = useState([]);
  const [regionDraft, setRegionDraft] = useState({});
  const loadKernelTab = async () => {
    try { const [k, g, r] = await Promise.all([api.kernelStatus(), api.geoipMmdb(), api.nodeRegions()]); setKernel(k); setGeoip(g); setRegions(r.regions || []); }
    catch (error) { if (!DEMO_MODE) setMessage(error.message); }
  };
  useEffect(() => { if (tab === "kernel") loadKernelTab(); }, [tab]);
  const loadRegions = async () => {
    try { setRegions((await api.nodeRegions()).regions || []); }
    catch (error) { if (!DEMO_MODE) setMessage(error.message); }
  };
  const saveRegion = async (key) => {
    const draft = regionDraft[key] || {};
    if (!draft.region) { setMessage("地区不能为空。"); return; }
    setKernelBusy(true); setMessage("");
    try {
      await api.assignNodeRegion(key, draft.country || "", draft.region);
      setMessage("节点地区已保存。");
      await loadRegions();
    } catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const kernelRun = async (fn, success) => {
    setKernelBusy(true); setMessage("");
    try {
      const result = await fn();
      const status = await api.kernelStatus();
      setKernel(status);
      setMessage(success);
      return result;
    } catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const checkKernel = async () => {
    setKernelBusy(true); setMessage("");
    try {
      const latest = await api.kernelCheck();
      const status = await api.kernelStatus();
      setKernel({ ...status, latest });
      setMessage(latest.version ? `最新版本 ${latest.version}（${latest.publishedAt ? shanghaiTime(new Date(latest.publishedAt).getTime() / 1000) : "未知时间"}）。` : "未找到最新版本。");
    } catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const uploadMmdb = async (file) => {
    setKernelBusy(true); setMessage("");
    try { setGeoip(await api.geoipMmdbUpload(file)); setMessage("GeoIP 离线地区库已更新。"); }
    catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const deleteMmdb = async () => {
    setKernelBusy(true); setMessage("");
    try { setGeoip(await api.geoipMmdbDelete()); setMessage("已删除离线地区库，回退到在线解析。"); }
    catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const downloadMmdb = async () => {
    setKernelBusy(true); setMessage("");
    try { setGeoip(await api.geoipMmdbDownload()); setMessage("已从默认源下载并安装 GeoIP 离线地区库。"); }
    catch (error) { setMessage(error.message); }
    finally { setKernelBusy(false); }
  };
  const loadDevices = () => api.deviceAliases().then(result => { setAliases(result.aliases || {}); setDevices(result.devices || []); }).catch(error => {
    if (DEMO_MODE) {
      const sample = [
        { ip: "192.168.1.20", name: "workstation", sourceType: "gateway", active: 3, lastSeen: Date.now() / 1000 },
        { ip: "192.168.1.30", name: "compute-node", sourceType: "gateway", active: 1, lastSeen: Date.now() / 1000 },
        { ip: "10.10.0.12", name: "remote-client", sourceType: "proxy", active: 2, lastSeen: Date.now() / 1000 },
      ];
      setDevices(sample); setAliases(Object.fromEntries(sample.map(item => [item.ip, item.name])));
    } else setMessage(error.message);
  });
  const loadRuntime = () => api.gatewayRuntime().then(setRuntime).catch(error => { if (DEMO_MODE) setRuntime(DEMO_GATEWAY.runtime); else setMessage(error.message); });
  const loadEvents = () => api.gatewayEvents({ level: eventLevel, query: eventQuery }).then(setEvents).catch(error => { if (DEMO_MODE) setEvents({ ...DEMO_GATEWAY.events, events: DEMO_GATEWAY.events.events.filter(item => eventLevel === "all" || item.level === eventLevel) }); else setMessage(error.message); });
  useEffect(() => { loadDevices(); loadRuntime(); loadEvents(); }, []);
  useEffect(() => { if (tab !== "runtime") return undefined; const timer = setInterval(loadRuntime, 5000); return () => clearInterval(timer); }, [tab]);
  useEffect(() => { if (tab === "events") loadEvents(); }, [tab, eventLevel]);
  const save = async () => {
    try { const result = await api.saveDeviceAliases(aliases); setAliases(result.aliases); setMessage("设备名称已保存，仪表盘会在下一次采样时更新。"); }
    catch (error) { setMessage(error.message); }
  };
  const toggleRow = key => setOpenRows(current => { const next = new Set(current); next.has(key) ? next.delete(key) : next.add(key); return next; });
  const known = [...new Map(devices.map(device => [device.ip, device])).values()];
  const statRow = (item, kind) => { const key = `${kind}:${item.id || item.name}`; const open = openRows.has(key); return <article className={`runtime-row ${open ? "open" : ""}`} key={key}><button className="runtime-row-head" onClick={() => toggleRow(key)}><span className={`runtime-mark ${kind}`}><i /></span><span><strong>{item.name}</strong><small>{kind === "access" ? `${item.devices?.length || 0} 台设备` : `${item.activeConnections || 0} 条活跃连接`}</small></span><b>{bytes(item.total)}</b><CaretDown /></button>{open && <div className="runtime-row-detail"><span><small>上传</small><strong>{bytes(item.up)}</strong></span><span><small>下载</small><strong>{bytes(item.down)}</strong></span><span><small>当前速度</small><strong>↑ {rate(item.currentUpRate)} · ↓ {rate(item.currentDownRate)}</strong></span><span><small>峰值速度</small><strong>↑ {rate(item.peakUpRate)} · ↓ {rate(item.peakDownRate)}</strong></span>{kind === "access" && item.devices?.length > 0 && <p>{item.devices.join(" · ")}</p>}</div>}</article>; };
  return <div className="page-content gateway-page">
    <div className="gateway-workspace-head"><h2>网关设置</h2><div className="gateway-tabs"><button className={tab === "runtime" ? "active" : ""} onClick={() => setTab("runtime")}>运行统计</button><button className={tab === "events" ? "active" : ""} onClick={() => setTab("events")}>事件记录</button><button className={tab === "devices" ? "active" : ""} onClick={() => setTab("devices")}>设备管理</button><button className={tab === "kernel" ? "active" : ""} onClick={() => setTab("kernel")}>内核与地区库</button></div>{tab === "devices" && canManage && <button className="primary-button" onClick={save}><CheckCircle /> 保存名称</button>}{tab === "runtime" && <button className="icon-action" aria-label="刷新运行统计" onClick={loadRuntime}><ArrowClockwise /></button>}{tab === "events" && <button className="icon-action" aria-label="刷新事件" onClick={loadEvents}><ArrowClockwise /></button>}</div>
    {message && <div className="inline-message">{message}</div>}
    {tab === "runtime" && <div className="gateway-runtime">
      <section className="panel runtime-summary"><div><span>启动时间</span><strong>{shanghaiDateTime(runtime?.startedAt)}</strong></div><div><span>运行时长</span><strong>{runtimeDuration(runtime?.uptimeSeconds)}</strong></div><div><span>累计流量</span><strong>{bytes(runtime?.total)}</strong></div><div><span>活跃出口</span><strong>{runtime?.activeExits ?? "—"}</strong></div></section>
      <section className="runtime-section"><div className="runtime-section-title"><h3>接入方式</h3><span className={runtime?.online ? "runtime-online" : "runtime-offline"}>{runtime?.online ? `mihomo ${runtime?.version || ""}` : "网关离线"}</span></div><div className="panel runtime-list">{(runtime?.access || []).map(item => statRow(item, "access"))}</div></section>
      <section className="runtime-section"><div className="runtime-section-title"><h3>出口与节点</h3><span>{runtime?.exits?.length || 0} 个已记录出口</span></div><div className="panel runtime-list">{(runtime?.exits || []).map(item => statRow(item, "exit"))}</div></section>
    </div>}
    {tab === "events" && <div className="gateway-events"><div className="event-toolbar"><div className="range-tabs">{[["all","全部"],["info","信息"],["warning","警告"],["error","错误"]].map(([value,label]) => <button key={value} className={eventLevel === value ? "active" : ""} onClick={() => setEventLevel(value)}>{label}</button>)}</div><form className="event-search" onSubmit={event => { event.preventDefault(); loadEvents(); }}><MagnifyingGlass /><input value={eventQuery} onChange={event => setEventQuery(event.target.value)} placeholder="搜索事件" /></form></div><section className="panel event-list">{events.events.length ? events.events.map(item => <article className={`event-row ${item.level}`} key={item.id}><span className="event-level">{item.level === "error" ? "错误" : item.level === "warning" ? "警告" : "信息"}</span><div><strong>{item.title}</strong>{item.message && <p>{item.message}</p>}<time>{shanghaiDateTime(item.createdAt)}</time></div></article>) : <div className="event-empty">没有符合条件的事件</div>}</section></div>}
    {tab === "devices" && <><section className="panel gateway-summary"><div><span>默认网关</span><strong>192.168.31.190</strong></div><div><span>透明 DNS</span><strong>198.18.0.2</strong></div><div><span>运行模式</span><strong>TUN + 显式代理</strong></div></section><section className="panel managed-devices"><div className="panel-heading"><h2>已识别设备</h2></div><div className="device-editor-head"><span>来源 IP</span><span>设备名称</span><span>接入方式</span><span>活跃连接</span><span>最后活动</span></div>{known.map(device => <div className="device-editor-row" key={device.ip}><code>{device.ip}</code><input disabled={!canManage} value={aliases[device.ip] ?? device.name ?? ""} onChange={event => setAliases(current => ({ ...current, [device.ip]: event.target.value }))} /><span className={`device-source ${device.sourceType || "unknown"}`}><i />{device.sourceType === "proxy" ? "显式代理" : device.sourceType === "gateway" ? "局域网网关" : "未知"}</span><span className={device.active ? "device-active" : "device-idle"}>{device.active || 0}</span><time>{device.active ? "正在活动" : shanghaiTime(device.lastSeen)}</time></div>)}</section></>}
    {tab === "kernel" && <div className="gateway-kernel">
      <section className="panel kernel-panel">
        <div className="kernel-panel-head"><h2>mihomo 内核</h2>{kernel?.pendingRestart && <b className="kernel-restart-badge">重启容器后生效</b>}<button className="filter-button" disabled={kernelBusy} onClick={checkKernel}>检查更新</button></div>
        <div className="kernel-grid">
          <span><small>运行版本</small><strong>{kernel?.runningVersion || "—"}</strong></span>
          <span><small>最新版本</small><strong>{kernel?.latest?.version || "—"}</strong></span>
          <span><small>架构</small><strong>{kernel?.arch || "—"}</strong></span>
          <span><small>当前暂存</small><strong>{kernel?.current || "镜像内置"}</strong></span>
        </div>
        <div className="kernel-actions">
          <input value={kernelVersion} onChange={event => setKernelVersion(event.target.value)} placeholder="下载指定版本，如 1.20.0" />
          <button className="filter-button" disabled={kernelBusy || !kernelVersion.trim()} onClick={() => kernelRun(() => api.kernelDownload(kernelVersion.trim()), "内核已下载并校验。")}>下载</button>
          <button className="filter-button" disabled={kernelBusy || !kernel?.latest?.version} onClick={() => kernelRun(() => api.kernelDownload(kernel.latest.version), "最新内核已下载并校验。")}>下载最新</button>
          <button className="primary-button" disabled={kernelBusy || !kernel?.current} onClick={() => kernelRun(() => api.kernelApply(kernel.current), "已切换当前版本，重启 mihomo 容器后生效。")}>应用</button>
          <button className="filter-button" disabled={kernelBusy} onClick={() => kernelRun(api.kernelRollback, "已回滚，重启 mihomo 容器后生效。")}>回滚</button>
        </div>
        <div className="kernel-staged">{kernel?.staged?.length ? kernel.staged.map(item => <div className="kernel-staged-row" key={item.version}><span>{item.version}</span><small>{(item.size / 1024 / 1024).toFixed(1)} MiB</small>{kernel.current === item.version && <b>当前</b>}<button className="filter-button" disabled={kernelBusy} onClick={() => kernelRun(() => api.kernelDelete(item.version), "暂存已删除。")}>删除</button></div>) : <div className="empty-rules">还没有暂存的内核版本</div>}</div>
      </section>
      <section className="panel kernel-panel">
        <div className="kernel-panel-head"><h2>GeoIP 离线地区库</h2><div className="kernel-panel-actions"><button className="primary-button" disabled={kernelBusy} onClick={downloadMmdb}>下载默认库</button><label className="filter-button"><input type="file" accept=".mmdb" hidden onChange={event => event.target.files?.[0] && uploadMmdb(event.target.files[0])} />上传 .mmdb</label>{geoip?.enabled && <button className="filter-button danger-link" onClick={() => confirm("删除离线地区库？将回退到在线解析。") && deleteMmdb()}>删除</button>}</div></div>
        {geoip?.downloadUrl && <div className="kernel-hint">默认库来源：<code>{geoip.downloadUrl}</code>（wp-statistics/GeoLite2-City，定时更新）</div>}
        <div className="kernel-grid">
          <span><small>状态</small><strong>{geoip?.enabled ? "离线库可用" : "未启用（在线兜底）"}</strong></span>
          <span><small>文件</small><strong>{geoip?.path ? geoip.path.split("/").pop() : "—"}</strong></span>
          <span><small>大小</small><strong>{geoip?.size ? `${(geoip.size / 1024 / 1024).toFixed(1)} MiB` : "—"}</strong></span>
          <span><small>更新时间</small><strong>{geoip?.modifiedAt ? shanghaiTime(geoip.modifiedAt) : "—"}</strong></span>
        </div>
      </section>
      <section className="panel kernel-panel">
        <div className="kernel-panel-head"><h2>节点地区库</h2><button className="filter-button" disabled={kernelBusy} onClick={loadRegions}>刷新</button></div>
        <div className="region-list">{regions.length ? regions.map(row => <div className="region-row" key={row.node_key}><span className="region-node" title={row.node_key}>{row.node_name}</span><em>{row.country || "—"}</em><input value={regionDraft[row.node_key]?.region ?? row.region ?? ""} onChange={event => setRegionDraft(current => ({ ...current, [row.node_key]: { country: row.country, region: event.target.value } }))} placeholder="地区，如 洛杉矶" /><small>{row.source === "geoip" ? "出口探测" : row.source === "manual" ? "手动" : "名称启发式"}{row.probed_ip ? ` · ${row.probed_ip}` : ""}</small><button className="filter-button" disabled={kernelBusy} onClick={() => saveRegion(row.node_key)}>保存</button></div>) : <div className="empty-rules">还没有地区记录；激活网关组合后会自动预填并出口探测。</div>}</div>
      </section>
    </div>}
  </div>;
}

const DEMO_SUBSCRIPTIONS = {
  subscriptions: [{
    id: "demo-provider", owner: "demo", name: "Example Provider", maskedUrl: "https://provider.example.com/••••",
    interval: 21600, enabled: true, gatewayEnabled: true, sourceFormat: "surge", nodeCount: 14, rawNodeCount: 16,
    filter: { includeRegex: "", excludeRegex: "剩余流量|到期|官网", excludeKeywords: ["套餐"], renameRules: [] },
    filterSource: "ai", filterPreview: { total: 16, kept: 14, excluded: 2, renamed: 0, excludedPreview: ["剩余流量 454 GB", "到期 2026-08-31"], keptPreview: [] },
    aiAnalysis: { reason: "识别并排除流量与到期提示节点。", confidence: 0.94, provider: "deepseek", model: "deepseek-chat" },
    usage: { upload: 31 * 1024 ** 3, download: 202 * 1024 ** 3, total: 687 * 1024 ** 3, expire: Date.parse("2026-08-31T21:48:00+08:00") / 1000 },
    fetchedAt: Date.parse("2026-08-12T23:15:00+08:00") / 1000, lastError: null,
    deliveryPaths: { surge: "#demo-surge", clash: "#demo-clash" },
  }],
  summary: { count: 1, nodes: 16, healthy: 1, gateway: "Example Provider" },
  ai: { provider: "deepseek", providerLabel: "DeepSeek", model: "deepseek-chat", configured: true },
};

const filterEditorFrom = (item, workspace = null) => {
  const config = workspace?.filter || item.filter || {};
  const preview = workspace?.preview || item.filterPreview || { total: item.rawNodeCount || item.nodeCount || 0, kept: item.nodeCount || 0, excluded: 0, renamed: 0 };
  return {
    id: item.id,
    name: item.name,
    includeRegex: config.includeRegex || "",
    excludeRegex: config.excludeRegex || "",
    excludeKeywords: (config.excludeKeywords || []).join("\n"),
    renameRules: (config.renameRules || []).map(rule => `${rule.pattern} => ${rule.replacement}`).join("\n"),
    instruction: "",
    source: item.filterSource || "manual",
    preview,
    analysis: item.aiAnalysis || {},
    aiBusy: false,
  };
};

const parseRenameRules = value => value.split("\n").map(line => {
  const divider = line.indexOf("=>");
  if (divider < 0) return null;
  const pattern = line.slice(0, divider).trim();
  return pattern ? { pattern, replacement: line.slice(divider + 2).trim() } : null;
}).filter(Boolean);

const filterPayloadFromEditor = editor => ({
  includeRegex: editor.includeRegex.trim(),
  excludeRegex: editor.excludeRegex.trim(),
  excludeKeywords: editor.excludeKeywords.split(/[\n,，]/).map(item => item.trim()).filter(Boolean),
  renameRules: parseRenameRules(editor.renameRules),
  source: editor.source,
});

const filterEditorSignature = editor => editor ? JSON.stringify([
  editor.id,
  editor.includeRegex,
  editor.excludeRegex,
  editor.excludeKeywords,
  editor.renameRules,
]) : "";

function SubscriptionMenuPopover({ anchor, children }) {
  const popoverRef = useRef(null);
  const [position, setPosition] = useState({ top: 0, left: 0, width: 206, visibility: "hidden" });

  useLayoutEffect(() => {
    if (!anchor) return undefined;
    const updatePosition = () => {
      const popover = popoverRef.current;
      if (!popover || !anchor.isConnected) return;
      const viewport = window.visualViewport;
      const viewportTop = viewport?.offsetTop || 0;
      const viewportLeft = viewport?.offsetLeft || 0;
      const viewportWidth = viewport?.width || window.innerWidth;
      const viewportHeight = viewport?.height || window.innerHeight;
      const margin = 12;
      const gap = 8;
      const width = Math.min(window.innerWidth <= 720 ? 224 : 206, viewportWidth - margin * 2);
      const anchorRect = anchor.getBoundingClientRect();
      const measuredHeight = Math.max(popover.scrollHeight + 2, popover.offsetHeight, 218);
      const maxHeight = Math.max(120, viewportHeight - margin * 2);
      const height = Math.min(measuredHeight, maxHeight);
      const roomBelow = viewportTop + viewportHeight - margin - anchorRect.bottom - gap;
      const roomAbove = anchorRect.top - viewportTop - margin - gap;
      const openUpward = roomBelow < height && roomAbove > roomBelow;
      const preferredTop = openUpward ? anchorRect.top - gap - height : anchorRect.bottom + gap;
      const top = Math.min(
        viewportTop + viewportHeight - margin - height,
        Math.max(viewportTop + margin, preferredTop),
      );
      const left = Math.min(
        viewportLeft + viewportWidth - margin - width,
        Math.max(viewportLeft + margin, anchorRect.right - width),
      );
      setPosition({ top, left, width, maxHeight, visibility: "visible" });
    };

    updatePosition();
    const frame = window.requestAnimationFrame(updatePosition);
    const resizeObserver = new ResizeObserver(updatePosition);
    resizeObserver.observe(popoverRef.current);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    window.visualViewport?.addEventListener("resize", updatePosition);
    window.visualViewport?.addEventListener("scroll", updatePosition);
    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      window.visualViewport?.removeEventListener("resize", updatePosition);
      window.visualViewport?.removeEventListener("scroll", updatePosition);
    };
  }, [anchor]);

  return createPortal(
    <div ref={popoverRef} className="subscription-menu-popover is-floating" role="menu" style={position}>{children}</div>,
    document.body,
  );
}

const ROTATION_FACTORS = [
  { key: "usage_balance", label: "用量均衡" },
  { key: "region_health", label: "地区健康" },
  { key: "region_latency", label: "地区延迟" },
  { key: "node_delay", label: "节点延迟" },
  { key: "diversity", label: "多样性" },
];

function SubscriptionsPage({ user, onStrategiesChanged }) {
  const [data, setData] = useState({ subscriptions: [], summary: { count: 0, nodes: 0, healthy: 0, gateway: null } });
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);
  const [openMenu, setOpenMenu] = useState(null);
  const [filterEditor, setFilterEditor] = useState(null);
  const [aiEditor, setAiEditor] = useState(null);
  const [combos, setCombos] = useState([]);
  const [comboEditor, setComboEditor] = useState(null);
  const [comboBusy, setComboBusy] = useState(false);
  const [nodesOpen, setNodesOpen] = useState(null);
  const [nodesData, setNodesData] = useState({});
  const toggleComboNodes = async (combo) => {
    if (nodesOpen === combo.id) { setNodesOpen(null); return; }
    setNodesOpen(combo.id);
    setComboBusy(true);
    try {
      const nodes = (await api.comboNodes(combo.id)).nodes || [];
      setNodesData(current => ({ ...current, [combo.id]: nodes }));
    }
    catch (error) { setMessage(error.message); setNodesOpen(null); }
    finally { setComboBusy(false); }
  };
  const loadCombos = async () => {
    try { setCombos((await api.combos()).combos || []); }
    catch { /* 组合列表不可用时保持现状 */ }
  };
  const load = async () => {
    try { setData(await api.subscriptions()); setError(false); }
    catch (caught) {
      if (DEMO_MODE) { setData(DEMO_SUBSCRIPTIONS); setMessage(""); setError(false); }
      else { setMessage(caught.message); setError(true); }
    }
  };
  useEffect(() => { load(); loadCombos(); }, []);
  useEffect(() => {
    const closeMenu = event => {
      if (!event.target.closest(".subscription-menu, .subscription-menu-popover")) setOpenMenu(null);
    };
    const closeOnEscape = event => { if (event.key === "Escape") setOpenMenu(null); };
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  useEffect(() => {
    if (!filterEditor?.id || filterEditor.aiBusy || DEMO_MODE) return undefined;
    const signature = filterEditorSignature(filterEditor);
    const subscriptionId = filterEditor.id;
    const payload = filterPayloadFromEditor(filterEditor);
    const timer = window.setTimeout(async () => {
      setFilterEditor(current => filterEditorSignature(current) === signature ? { ...current, previewBusy: true, previewError: "" } : current);
      try {
        const result = await api.previewSubscriptionFilter(subscriptionId, payload);
        setFilterEditor(current => filterEditorSignature(current) === signature ? { ...current, preview: result.preview, previewBusy: false, previewError: "" } : current);
      } catch (caught) {
        setFilterEditor(current => filterEditorSignature(current) === signature ? { ...current, previewBusy: false, previewError: caught.message } : current);
      }
    }, 350);
    return () => window.clearTimeout(timer);
  }, [filterEditor?.id, filterEditor?.includeRegex, filterEditor?.excludeRegex, filterEditor?.excludeKeywords, filterEditor?.renameRules, filterEditor?.aiBusy]);
  const run = async (key, action, success) => {
    setBusy(key); setMessage(""); setError(false);
    try { const result = await action(); await load(); setMessage(typeof success === "function" ? success(result) : success); return true; }
    catch (caught) { setMessage(caught.message); setError(true); return false; }
    finally { setBusy(""); }
  };
  const save = async (event) => {
    event.preventDefault();
    const payload = { name: editor.name, interval: Number(editor.interval), enabled: editor.enabled, urlRepeatable: Boolean(editor.urlRepeatable) };
    if (!editor.id || editor.url) payload.url = editor.url;
    const ok = await run(editor.id || "create", () => editor.id ? api.updateSubscription(editor.id, payload) : api.createSubscription(payload), result => result.subscription?.lastError ? `订阅已保存，但首次拉取失败：${result.subscription.lastError}` : editor.id ? "订阅设置已更新。" : "订阅已添加并完成首次解析。");
    if (ok) setEditor(null);
  };
  const openFilter = async (item) => {
    setOpenMenu(null); setBusy(`filter-${item.id}`); setMessage(""); setError(false);
    try {
      const workspace = await api.subscriptionFilter(item.id);
      setFilterEditor(filterEditorFrom(item, workspace));
    } catch (caught) {
      if (DEMO_MODE) setFilterEditor(filterEditorFrom(item));
      else { setMessage(caught.message); setError(true); }
    } finally { setBusy(""); }
  };
  const saveCombo = async (event) => {
    event.preventDefault();
    setComboBusy(true); setMessage(""); setError(false);
    try {
      const { id, pool, strategyLabel, state, lastError, createdAt, updatedAt, gatewayEnabled, ...payload } = comboEditor;
      if (!payload.subscriptionIds?.length) throw new Error("组合至少需要一个订阅");
      const result = id ? await api.updateCombo(id, payload) : await api.createCombo(payload);
      await loadCombos(); await load();
      setComboEditor(null);
      setMessage(id ? "组合已更新。" : "组合已创建，可在卡片上设为网关节点源。");
    } catch (caught) { setMessage(caught.message); setError(true); }
    finally { setComboBusy(false); }
  };
  const comboAction = async (combo, action, success) => {
    setComboBusy(true); setMessage(""); setError(false);
    try {
      if (action === "activate") await api.activateCombo(combo.id);
      else if (action === "deactivate") await api.deactivateCombo(combo.id);
      else if (action === "rotate") await api.rotateCombo(combo.id);
      else if (action === "cross") await api.crossRegionCombo(combo.id);
      else if (action === "probe") await api.probeComboRegions(combo.id);
      else if (action === "rotate-token") await api.rotateComboToken(combo.id);
      else if (action === "delete") await api.deleteCombo(combo.id);
      await loadCombos(); await load();
      // 轮换/跨区/激活等会改动 mihomo 选择器，同步刷新分流策略页，避免策略页停留在旧快照。
      if (onStrategiesChanged && ["rotate", "cross", "activate", "deactivate"].includes(action)) await onStrategiesChanged();
      setMessage(success);
    } catch (caught) { setMessage(caught.message); setError(true); }
    finally { setComboBusy(false); }
  };
  const analyzeFilter = async () => {
    const current = filterEditor;
    setFilterEditor({ ...current, aiBusy: true });
    try {
      const result = await api.analyzeSubscriptionFilter(current.id, current.instruction);
      const suggestion = result.analysis;
      setFilterEditor({
        ...current,
        includeRegex: suggestion.filter.includeRegex || "",
        excludeRegex: suggestion.filter.excludeRegex || "",
        excludeKeywords: (suggestion.filter.excludeKeywords || []).join("\n"),
        renameRules: (suggestion.filter.renameRules || []).map(rule => `${rule.pattern} => ${rule.replacement}`).join("\n"),
        source: "ai",
        preview: suggestion.preview,
        analysis: suggestion,
        aiBusy: false,
      });
    } catch (caught) {
      if (DEMO_MODE) {
        setFilterEditor({
          ...current,
          excludeRegex: "剩余流量|到期|官网|套餐",
          source: "ai",
          preview: { total: 16, kept: 14, excluded: 2, renamed: 0, excludedPreview: ["剩余流量 454 GB", "到期 2026-08-31"] },
          analysis: { reason: "识别到两个套餐信息节点，建议从交付配置中排除。", confidence: 0.94, provider: "deepseek", model: "deepseek-chat" },
          aiBusy: false,
        });
      } else {
        setFilterEditor({ ...current, aiBusy: false });
        setMessage(caught.message); setError(true);
      }
    }
  };
  const saveFilter = async (event) => {
    event.preventDefault();
    const current = filterEditor;
    const payload = filterPayloadFromEditor(current);
    setBusy(`filter-${current.id}`);
    try {
      if (!DEMO_MODE) await api.updateSubscriptionFilter(current.id, payload);
      await load();
      setFilterEditor(null); setMessage("节点过滤已保存，交付配置与网关节点库存已同步更新。"); setError(false);
    } catch (caught) { setMessage(caught.message); setError(true); }
    finally { setBusy(""); }
  };
  const openAISettings = async () => {
    setBusy("ai-settings"); setMessage(""); setError(false);
    try {
      const result = await api.aiSettings();
      setAiEditor({ ...result.settings, originalProvider: result.settings.provider, originalKeyConfigured: result.settings.apiKeyConfigured, apiKey: "", clearApiKey: false });
    } catch (caught) {
      if (DEMO_MODE) setAiEditor({ provider: "deepseek", originalProvider: "deepseek", model: "deepseek-chat", apiKeyConfigured: true, originalKeyConfigured: true, apiKey: "", clearApiKey: false });
      else { setMessage(caught.message); setError(true); }
    } finally { setBusy(""); }
  };
  const saveAISettings = async (event) => {
    event.preventDefault();
    setBusy("ai-settings-save");
    try {
      const payload = { provider: aiEditor.provider, model: aiEditor.model, clearApiKey: aiEditor.clearApiKey };
      if (aiEditor.apiKey) payload.apiKey = aiEditor.apiKey;
      if (!DEMO_MODE) await api.updateAISettings(payload);
      await load(); setAiEditor(null); setMessage("AI 模型配置已保存。"); setError(false);
    } catch (caught) { setMessage(caught.message); setError(true); }
    finally { setBusy(""); }
  };
  const copyDelivery = async (item, client) => {
    const delivery = new URL(item.deliveryPaths?.[client], location.origin).toString();
    const label = client === "surge" ? "Surge" : "Clash/Mihomo";
    try { await navigator.clipboard.writeText(delivery); setMessage(`${label} 完整配置地址已复制。`); setError(false); }
    catch { setMessage(`复制失败，请手动复制：${delivery}`); setError(true); }
  };
  const items = data.subscriptions || [];
  return <div className="page-content subscriptions-page">
    <div className="subscriptions-hero"><h2>订阅与节点来源</h2><div className="subscription-hero-actions">{user?.role === "admin" && <button className="filter-button" disabled={Boolean(busy)} onClick={openAISettings}><Lightning weight="fill" /> AI 模型</button>}<button className="primary-button" onClick={() => setEditor({ name: "", url: "", interval: 21600, enabled: true, urlRepeatable: false })}><Plus weight="bold" /> 添加订阅</button></div></div>
    {message && <div className={`inline-message ${error ? "is-error" : ""}`}>{error ? <WarningCircle /> : <CheckCircle />}{message}</div>}
    <section className={`subscription-ai-strip ${data.ai?.configured ? "configured" : ""}`}><span className="subscription-ai-icon"><Lightning weight="fill" /></span><div><strong>节点过滤助手</strong><b>{data.ai?.configured ? `${data.ai.providerLabel} · ${data.ai.model}` : "等待管理员配置模型"}</b></div><p>AI 只接收节点名称与协议，不会收到服务器、密码或订阅地址。</p></section>
    <div className="subscription-stats"><div><span>订阅来源</span><strong>{data.summary?.count ?? 0}</strong></div><div><span>可用节点库存</span><strong>{data.summary?.nodes ?? 0}</strong></div><div><span>网关活动源</span><strong>{data.summary?.gateway || "未设置"}</strong></div><div><span>自动刷新</span><strong>{items.filter(item => item.enabled && item.urlRepeatable).length}</strong></div></div>
    <section className="panel subscription-panel">
      <div className="subscription-panel-head"><h3>订阅列表</h3><button className="filter-button" disabled={Boolean(busy)} onClick={() => run("all", async () => { for (const item of items.filter(row => row.enabled)) await api.refreshSubscription(item.id); }, "所有已启用订阅均已刷新。") }><ArrowClockwise /> 刷新全部</button></div>
      {items.length ? <div className="subscription-list">{items.map(item => {
        const used = Number(item.usage?.upload || 0) + Number(item.usage?.download || 0);
        const total = Number(item.usage?.total || 0);
        const percent = total ? Math.min(100, used / total * 100) : 0;
        return <article className={`subscription-card ${item.gatewayEnabled ? "is-gateway" : ""} ${openMenu?.id === item.id ? "menu-open" : ""}`} key={item.id}>
          <div className="subscription-source"><span className={`subscription-health ${item.lastError ? "failed" : item.fetchedAt ? "healthy" : "pending"}`}><CloudArrowDown weight="fill" /></span><div><div className="subscription-title"><h3>{item.name}</h3>{item.gatewayEnabled && <b>网关节点源</b>}{!item.urlRepeatable && item.fetchedAt && <em className="subscription-onetime-badge">一次性</em>}{item.filterPreview?.excluded > 0 && <em className="subscription-filter-badge">{item.filterSource === "ai" ? "AI 过滤" : "已过滤"} {item.filterPreview.excluded}</em>}{user?.role === "admin" && item.owner !== user.username && <em>{item.owner}</em>}</div><p>{item.maskedUrl}</p><div className="subscription-node-count"><HardDrives /><strong>{item.nodeCount || 0}</strong><span>{item.rawNodeCount > item.nodeCount ? `/ ${item.rawNodeCount} 个节点` : "个节点"}</span>{item.lastError && <b>刷新失败</b>}</div></div></div>
          <div className="subscription-quota"><div className="subscription-quota-value"><strong>{total ? bytes(used) : "—"}</strong><span>{total ? `已用 / ${bytes(total)}` : "来源未提供配额"}</span></div><i><u style={{ width: `${percent}%` }} /></i>{total > 0 && <b>{percent.toFixed(1)}%</b>}<div className="subscription-lifecycle"><span><b>到期时间</b><time>{item.usage?.expire ? shanghaiTime(item.usage.expire) : "未提供"}</time></span><span><b>更新时间</b><time>{item.lastError ? "刷新失败" : shanghaiTime(item.fetchedAt)}</time></span></div></div>
          <div className="subscription-card-actions">
            <div className="subscription-card-toolbar">
              {user?.role === "admin" ? <button className={`subscription-gateway-status ${item.gatewayEnabled ? "active" : ""}`} disabled={Boolean(busy) || (!item.gatewayEnabled && !item.nodeCount)} onClick={() => run(`gateway-${item.id}`, () => item.gatewayEnabled ? api.deactivateSubscription(item.id) : api.activateSubscription(item.id), item.gatewayEnabled ? "已停用订阅覆盖，网关恢复基础节点配置。" : "订阅已成为网关节点源，并已热重载。") }><span />{item.gatewayEnabled ? "网关使用中" : "用于网关"}</button> : <span className={`subscription-gateway-status ${item.gatewayEnabled ? "active" : ""}`}><span />{item.gatewayEnabled ? "网关使用中" : "个人订阅"}</span>}
              <div className="subscription-menu">
                <button className="subscription-menu-trigger" aria-label={`管理 ${item.name}`} aria-expanded={openMenu?.id === item.id} onClick={event => { event.stopPropagation(); const anchor = event.currentTarget; setOpenMenu(current => current?.id === item.id ? null : { id: item.id, anchor }); }}><DotsThreeVertical weight="bold" /></button>
                {openMenu?.id === item.id && <SubscriptionMenuPopover anchor={openMenu.anchor}>
                  <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(null); run(item.id, () => api.refreshSubscription(item.id), "订阅已刷新；节点库存与状态已更新。"); }}><ArrowClockwise className={busy === item.id ? "spinning" : ""} />立即刷新</button>
                  <button role="menuitem" disabled={Boolean(busy)} onClick={() => openFilter(item)}><Funnel />节点过滤</button>
                  <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(null); setEditor({ id: item.id, name: item.name, url: "", interval: item.interval, enabled: item.enabled, urlRepeatable: item.urlRepeatable }); }}><PencilSimple />编辑订阅</button>
                  <button role="menuitem" disabled={Boolean(busy)} onClick={() => { setOpenMenu(null); if (confirm(`轮换「${item.name}」的交付链接？旧链接会立即失效。`)) run(`rotate-${item.id}`, () => api.rotateSubscriptionToken(item.id), "交付链接已轮换，旧链接已失效。"); }}><LinkSimple />轮换交付链接</button>
                  <button role="menuitem" className="danger" disabled={Boolean(busy)} onClick={() => { setOpenMenu(null); if (confirm(`删除订阅「${item.name}」？交付地址将立即失效。`)) run(`delete-${item.id}`, () => api.deleteSubscription(item.id), "订阅已删除。"); }}><Trash />删除订阅</button>
                </SubscriptionMenuPopover>}
              </div>
            </div>
            <div className="subscription-deliveries" aria-label={`${item.name} 配置链接`}>
              <div className="subscription-delivery"><AppleLogo weight="fill" /><span>Surge 配置</span><button title="复制 Surge 配置链接" onClick={() => copyDelivery(item, "surge")}><Copy /></button><a title="打开 Surge 配置" href={item.deliveryPaths?.surge} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
              <div className="subscription-delivery"><FileCode weight="fill" /><span>Clash / Mihomo</span><button title="复制 Clash/Mihomo 配置链接" onClick={() => copyDelivery(item, "clash")}><Copy /></button><a title="打开 Clash/Mihomo 配置" href={item.deliveryPaths?.clash} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
            </div>
          </div>
          {item.lastError && <div className="subscription-error"><WarningCircle />{item.lastError}</div>}
        </article>;
      })}</div> : <div className="subscription-empty"><CloudArrowDown /><h3>还没有订阅</h3><p>添加节点来源后，可定时刷新、生成隔离交付地址；管理员还可以把它设为网关节点源。</p><button className="primary-button" onClick={() => setEditor({ name: "", url: "", interval: 21600, enabled: true })}>添加第一个订阅</button></div>}
    </section>
    {<section className="panel combo-panel">
      <div className="combo-panel-head"><h3>组合配置表</h3><button className="filter-button" disabled={comboBusy} onClick={() => setComboEditor({ name: "", subscriptionIds: [], strategy: "smart", rotateIntervalSeconds: 1800, crossRegionIntervalSeconds: 259200, enabled: true, rotationPrefs: [] })}>新建组合</button></div>
      {combos.length ? <div className="combo-list">{combos.map(combo => (
        <article className={`combo-card ${combo.gatewayEnabled ? "is-gateway" : ""}`} key={combo.id}>
          <div className="combo-head">
            <div className="combo-title"><h3>{combo.name}</h3>{combo.gatewayEnabled && <b>网关节点源</b>}<em>{combo.strategyLabel}</em>{combo.rotationPrefs?.length > 0 && <em className="combo-ai-badge">因素轮换</em>}</div>
            <div className="combo-meta"><span><HardDrives />{combo.pool?.nodeCount ?? 0} 个节点</span><span>{combo.pool?.countries?.length ? combo.pool.countries.map(item => `${item.country} ${item.count}`).join(" · ") : "—"}</span></div>
            <div className="combo-state">
              <div className="combo-country-list">
                {combo.pool?.countries?.length ? combo.pool.countries.map(({ country, count, flag }) => {
                  const st = combo.state?.countries?.[country] || {};
                  return <div className={`combo-country-row ${st.node ? "has-exit" : ""}`} key={country}>
                    <b>{flag || ""} {country} <small>{count}</small></b>
                    <span className="combo-country-node" title={st.node || "尚未轮换"}>{st.node || "待轮换"}</span>
                    <small className="combo-country-region">{st.region && st.region !== "默认" ? st.region : "未识别"}{st.lastCrossAt ? ` · ${shanghaiTime(st.lastCrossAt)} 跨区` : ""}</small>
                  </div>;
                }) : <div className="empty-rules">节点池为空</div>}
              </div>
              <div className="combo-state-meta"><span>跨地区 {combo.crossRegionIntervalSeconds >= 86400 ? `${combo.crossRegionIntervalSeconds / 86400} 天` : `${combo.crossRegionIntervalSeconds / 3600} 小时`}</span>{combo.rotationPrefs?.length > 0 && <span>按因素择优</span>}</div>
            </div>
            {user?.role === "admin" && <div className="combo-gateway-actions">
              <button className={`subscription-gateway-status ${combo.gatewayEnabled ? "active" : ""}`} disabled={comboBusy || (!combo.gatewayEnabled && !combo.pool?.nodeCount)} onClick={() => comboAction(combo, combo.gatewayEnabled ? "deactivate" : "activate", combo.gatewayEnabled ? "组合已停用，网关恢复基础配置。" : "组合已设为网关节点源并热重载。")}><span />{combo.gatewayEnabled ? "网关使用中" : "用于网关"}</button>
              <button className="filter-button" disabled={comboBusy || !combo.gatewayEnabled} onClick={() => comboAction(combo, "rotate", "已按当前策略轮换出口。")}>立即轮换</button>
              <button className="filter-button" disabled={comboBusy || !combo.gatewayEnabled} onClick={() => comboAction(combo, "cross", "已跨地区切换出口。")}>跨地区</button>
              <button className="filter-button" disabled={comboBusy || !combo.gatewayEnabled} onClick={() => comboAction(combo, "probe", "出口地区探测完成。")}>探测地区</button>
            </div>}
          </div>
          {combo.lastError && <div className="subscription-error"><WarningCircle />{combo.lastError}</div>}
          {nodesOpen === combo.id && <div className="combo-nodes">
            {nodesData[combo.id]?.length ? <div className="combo-nodes-table">
              <div className="combo-nodes-head"><span>国家</span><span>节点</span><span>出口地区</span><span>来源</span><span>出口 IP</span></div>
              {nodesData[combo.id].map(node => <div className={`combo-node-row ${node.isCurrent ? "current" : ""}`} key={node.name}><b>{node.flag} {node.country}</b><span className="combo-node-name" title={node.name}>{node.name}{node.isCurrent && <em>当前出口</em>}</span><span>{node.region}</span><small>{node.source === "geoip" ? "出口探测" : node.source === "manual" ? "手动" : "名称"}</small><code>{node.probedIp || "—"}</code></div>)}
            </div> : <div className="empty-rules">正在加载节点出口明细…</div>}
          </div>}
          {combo.deliveryPaths && <div className="combo-foot">
            <span className="combo-foot-label"><LinkSimple />组合配置</span>
            <div className="subscription-delivery"><AppleLogo weight="fill" /><span>Surge</span><button title="复制 Surge 配置链接" onClick={() => copyDelivery(combo, "surge")}><Copy /></button><a title="打开 Surge 配置" href={combo.deliveryPaths.surge} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
            <div className="subscription-delivery"><FileCode weight="fill" /><span>Clash / Mihomo</span><button title="复制 Clash/Mihomo 配置链接" onClick={() => copyDelivery(combo, "clash")}><Copy /></button><a title="打开 Clash/Mihomo 配置" href={combo.deliveryPaths.clash} target="_blank" rel="noreferrer"><DownloadSimple /></a></div>
            <button className="filter-button" disabled={comboBusy} onClick={() => toggleComboNodes(combo)}>{nodesOpen === combo.id ? "收起出口明细" : "节点出口明细"}</button>
            <button className="filter-button" disabled={comboBusy} onClick={() => confirm(`轮换「${combo.name}」的组合配置链接？旧链接会立即失效。`) && comboAction(combo, "rotate-token", "组合配置链接已轮换。")}><LinkSimple />轮换链接</button>
            <button className="filter-button" disabled={comboBusy} onClick={() => setComboEditor({ id: combo.id, name: combo.name, subscriptionIds: [...(combo.subscriptionIds || [])], strategy: combo.strategy, rotateIntervalSeconds: combo.rotateIntervalSeconds, crossRegionIntervalSeconds: combo.crossRegionIntervalSeconds, enabled: combo.enabled, rotationPrefs: [...(combo.rotationPrefs || [])] })}>编辑</button>
            <button className="filter-button danger-link" disabled={comboBusy} onClick={() => confirm(`删除组合「${combo.name}」？`) && comboAction(combo, "delete", "组合已删除。")}>删除</button>
          </div>}
        </article>
      ))}</div> : <div className="empty-rules">还没有组合；把多个订阅合并成节点池，生成一份合并配置供客户端使用。</div>}
    </section>}
    {editor && <div className="modal-backdrop" onMouseDown={() => setEditor(null)}><form className="user-modal subscription-modal" role="dialog" aria-modal="true" aria-labelledby="subscription-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={save}><div className="modal-heading"><div><span className="eyebrow">节点来源</span><h3 id="subscription-editor-title">{editor.id ? "编辑订阅" : "添加订阅"}</h3></div><button type="button" aria-label="关闭订阅编辑器" onClick={() => setEditor(null)}><X /></button></div><label>名称<input required autoFocus value={editor.name} onChange={event => setEditor({ ...editor, name: event.target.value })} placeholder="例如 Example Provider" /></label><label>订阅地址<input required={!editor.id} type="url" value={editor.url} onChange={event => setEditor({ ...editor, url: event.target.value })} placeholder={editor.id ? "留空表示保留当前地址" : "https://example.com/subscribe"} /><small>地址视为凭据保存，不会在列表或 API 响应中明文返回。</small></label><label className="subscription-link-type">链接类型<span className="subscription-link-toggle"><button type="button" className={!editor.urlRepeatable ? "active" : ""} onClick={() => setEditor({ ...editor, urlRepeatable: false, enabled: true })}>一次性</button><button type="button" className={editor.urlRepeatable ? "active" : ""} onClick={() => setEditor({ ...editor, urlRepeatable: true })}>可重复</button></span></label>{editor.urlRepeatable ? <div className="modal-fields"><label>刷新周期<select value={editor.interval} onChange={event => setEditor({ ...editor, interval: Number(event.target.value) })}><option value={3600}>1 小时</option><option value={21600}>6 小时</option><option value={43200}>12 小时</option><option value={86400}>24 小时</option><option value={604800}>7 天</option></select></label><label className="subscription-enabled">自动刷新<span><input type="checkbox" checked={editor.enabled} onChange={event => setEditor({ ...editor, enabled: event.target.checked })} />启用</span></label></div> : <p className="subscription-onetime-hint">一次性链接：导入时拉取一次，之后不自动刷新；更新节点请重新获取订阅链接后再次导入。</p>}<button className="primary-button modal-submit" disabled={Boolean(busy)}>{busy ? "正在保存与解析…" : "保存订阅"}</button></form></div>}
    {comboEditor && <div className="modal-backdrop" onMouseDown={() => setComboEditor(null)}><form className="user-modal subscription-modal combo-editor-modal" role="dialog" aria-modal="true" aria-labelledby="combo-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveCombo}><div className="modal-heading"><div><span className="eyebrow">订阅组合</span><h3 id="combo-editor-title">{comboEditor.id ? "编辑组合" : "新建组合"}</h3></div><button type="button" aria-label="关闭组合编辑器" onClick={() => setComboEditor(null)}><X /></button></div><label>组合名称<input required autoFocus value={comboEditor.name} onChange={event => setComboEditor({ ...comboEditor, name: event.target.value })} placeholder="例如 主力组合" /></label><label>包含订阅<div className="combo-subscription-picker">{items.map(item => <label key={item.id} className="combo-pick"><input type="checkbox" checked={comboEditor.subscriptionIds.includes(item.id)} onChange={event => setComboEditor({ ...comboEditor, subscriptionIds: event.target.checked ? [...comboEditor.subscriptionIds, item.id] : comboEditor.subscriptionIds.filter(id => id !== item.id) })} /><span>{item.name}</span><small>{item.nodeCount || 0} 节点</small></label>)}</div></label><div className="modal-fields"><label>地区内轮换间隔<select value={comboEditor.rotateIntervalSeconds} onChange={event => setComboEditor({ ...comboEditor, rotateIntervalSeconds: Number(event.target.value) })}><option value={900}>15 分钟</option><option value={1800}>30 分钟</option><option value={3600}>1 小时</option><option value={21600}>6 小时</option><option value={86400}>1 天</option></select></label><label>跨地区间隔<select value={comboEditor.crossRegionIntervalSeconds} onChange={event => setComboEditor({ ...comboEditor, crossRegionIntervalSeconds: Number(event.target.value) })}><option value={43200}>12 小时</option><option value={86400}>1 天</option><option value={259200}>3 天</option><option value={604800}>7 天</option></select></label></div><div className="modal-fields"><label className="subscription-enabled">轮换<span><input type="checkbox" checked={comboEditor.enabled} onChange={event => setComboEditor({ ...comboEditor, enabled: event.target.checked })} />启用</span></label></div><div className="rotation-prefs-editor"><span className="rotation-prefs-title">轮换偏好 <small>勾选后参与排序，数字越小优先级越高</small></span>{ROTATION_FACTORS.map(factor => {
    const prefs = comboEditor.rotationPrefs || [];
    const enabled = prefs.includes(factor.key);
    const order = enabled ? prefs.indexOf(factor.key) + 1 : 0;
    const toggle = () => setComboEditor({ ...comboEditor, rotationPrefs: enabled ? prefs.filter(k => k !== factor.key) : [...prefs, factor.key] });
    const move = delta => {
      const idx = prefs.indexOf(factor.key);
      const swap = idx + delta;
      if (idx < 0 || swap < 0 || swap >= prefs.length) return;
      const next = [...prefs];
      [next[idx], next[swap]] = [next[swap], next[idx]];
      setComboEditor({ ...comboEditor, rotationPrefs: next });
    };
    return <label key={factor.key} className={`rotation-factor-row ${enabled ? "on" : ""}`}><input type="checkbox" checked={enabled} onChange={toggle} /><span className="rotation-factor-name">{factor.label}</span>{enabled && <span className="rotation-factor-order">{order}</span>}<span className="rotation-factor-actions"><button type="button" disabled={!enabled || order <= 1} onClick={event => { event.preventDefault(); move(-1); }} aria-label="上移">↑</button><button type="button" disabled={!enabled || order >= prefs.length} onClick={event => { event.preventDefault(); move(1); }} aria-label="下移">↓</button></span></label>;
  })}</div><button className="primary-button modal-submit" disabled={comboBusy}>{comboBusy ? "处理中…" : "保存组合"}</button></form></div>}
    {filterEditor && <div className="modal-backdrop" onMouseDown={() => !filterEditor.aiBusy && setFilterEditor(null)}><form className="user-modal subscription-filter-modal" role="dialog" aria-modal="true" aria-labelledby="filter-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveFilter}>
      <div className="modal-heading"><div><span className="eyebrow">节点过滤</span><h3 id="filter-editor-title">{filterEditor.name}</h3></div><button type="button" aria-label="关闭节点过滤" disabled={filterEditor.aiBusy} onClick={() => setFilterEditor(null)}><X /></button></div>
      <div className="filter-preview-grid"><span><small>原始节点</small><strong>{filterEditor.preview?.total ?? 0}</strong></span><span><small>保留</small><strong>{filterEditor.preview?.kept ?? 0}</strong></span><span><small>排除</small><strong>{filterEditor.preview?.excluded ?? 0}</strong></span><span><small>改名</small><strong>{filterEditor.preview?.renamed ?? 0}</strong></span></div>
      <section className="ai-filter-assistant"><div><Lightning weight="fill" /><span><strong>AI 自动识别</strong><b>{data.ai?.configured ? `${data.ai.providerLabel} · ${data.ai.model}` : "模型尚未配置"}</b></span></div><textarea value={filterEditor.instruction} onChange={event => setFilterEditor({ ...filterEditor, instruction: event.target.value })} placeholder="可选：例如保留家宽节点，排除倍率大于 2 的节点" /><button type="button" disabled={!data.ai?.configured || filterEditor.aiBusy} onClick={analyzeFilter}>{filterEditor.aiBusy ? "正在分析节点…" : "生成过滤建议"}</button></section>
      {filterEditor.analysis?.reason && <div className="ai-filter-result"><strong>{Math.round(Number(filterEditor.analysis.confidence || 0) * 100)}% 置信度</strong><span>{filterEditor.analysis.reason}</span></div>}
      <div className="filter-form-grid"><label>包含正则<input autoFocus value={filterEditor.includeRegex} onChange={event => setFilterEditor({ ...filterEditor, includeRegex: event.target.value, source: "manual", analysis: {} })} placeholder="留空表示保留所有地区节点" /></label><label>排除正则<input value={filterEditor.excludeRegex} onChange={event => setFilterEditor({ ...filterEditor, excludeRegex: event.target.value, source: "manual", analysis: {} })} placeholder="剩余流量|到期|官网" /></label></div>
      <label>排除关键词<textarea value={filterEditor.excludeKeywords} onChange={event => setFilterEditor({ ...filterEditor, excludeKeywords: event.target.value, source: "manual", analysis: {} })} placeholder={"每行一个，例如：\n套餐\n流量重置"} /></label>
      <label>节点改名规则<textarea value={filterEditor.renameRules} onChange={event => setFilterEditor({ ...filterEditor, renameRules: event.target.value, source: "manual", analysis: {} })} placeholder={"每行一条：正则 => 替换内容\nHong Kong => 香港\nUSA Seattle => 美国西雅图"} /></label>
      {filterEditor.previewError && <div className="filter-preview-error"><WarningCircle />{filterEditor.previewError}</div>}
      {filterEditor.preview?.excludedPreview?.length > 0 && <div className="filter-node-preview"><span>将排除</span>{filterEditor.preview.excludedPreview.map(name => <code key={name}>{name}</code>)}</div>}
      {filterEditor.preview?.renamedPreview?.length > 0 && <div className="filter-node-preview renamed"><span>将改名</span>{filterEditor.preview.renamedPreview.map((item, index) => <code key={`${item.from}-${index}`}>{item.from} → {item.to}</code>)}</div>}
      <button className="primary-button modal-submit" disabled={Boolean(busy) || filterEditor.aiBusy || filterEditor.previewBusy || Boolean(filterEditor.previewError)}>{busy ? "正在应用…" : "保存并应用"}</button>
    </form></div>}
    {aiEditor && <div className="modal-backdrop" onMouseDown={() => setAiEditor(null)}><form className="user-modal ai-settings-modal" role="dialog" aria-modal="true" aria-labelledby="ai-editor-title" onMouseDown={event => event.stopPropagation()} onSubmit={saveAISettings}>
      <div className="modal-heading"><div><span className="eyebrow">全局配置</span><h3 id="ai-editor-title">AI 模型</h3></div><button type="button" aria-label="关闭 AI 设置" onClick={() => setAiEditor(null)}><X /></button></div>
      <div className="ai-provider-picker"><button type="button" className={aiEditor.provider === "deepseek" ? "active" : ""} onClick={() => setAiEditor({ ...aiEditor, provider: "deepseek", model: aiEditor.provider === "deepseek" ? aiEditor.model : "deepseek-chat", apiKeyConfigured: aiEditor.originalProvider === "deepseek" && aiEditor.originalKeyConfigured, apiKey: "", clearApiKey: false })}>DeepSeek</button><button type="button" className={aiEditor.provider === "openrouter" ? "active" : ""} onClick={() => setAiEditor({ ...aiEditor, provider: "openrouter", model: aiEditor.provider === "openrouter" ? aiEditor.model : "deepseek/deepseek-chat-v3.1", apiKeyConfigured: aiEditor.originalProvider === "openrouter" && aiEditor.originalKeyConfigured, apiKey: "", clearApiKey: false })}>OpenRouter</button></div>
      <label>模型名称<input required autoFocus value={aiEditor.model} onChange={event => setAiEditor({ ...aiEditor, model: event.target.value })} placeholder={aiEditor.provider === "deepseek" ? "deepseek-chat" : "provider/model"} /></label>
      <label>API Key<input required={!aiEditor.apiKeyConfigured} type="password" autoComplete="new-password" value={aiEditor.apiKey} onChange={event => setAiEditor({ ...aiEditor, apiKey: event.target.value, clearApiKey: false })} placeholder={aiEditor.apiKeyConfigured ? "已配置；留空表示保留" : "输入此提供商的 API Key"} /></label>
      {aiEditor.apiKeyConfigured && <label className="subscription-enabled">移除现有密钥<span><input type="checkbox" checked={aiEditor.clearApiKey} onChange={event => setAiEditor({ ...aiEditor, clearApiKey: event.target.checked, apiKey: "" })} />清除</span></label>}
      <div className="ai-security-note"><ShieldCheck weight="fill" /><span>模型只接收节点名称和协议类型；密钥不会返回给浏览器。</span></div>
      <button className="primary-button modal-submit" disabled={Boolean(busy)}>{busy ? "正在保存…" : "保存模型配置"}</button>
    </form></div>}
  </div>;
}

const normalizePage = value => {
  const current = value === "system" ? "users" : value;
  return pageDefinition(current) ? current : "dashboard";
};

export function App() {
  const [page, setPage] = useState(() => normalizePage(new URLSearchParams(location.search).get("page")));
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("egresscope-theme") || localStorage.getItem("ssslab-theme") || "system");
  const [dashboard, setDashboard] = useState(DEMO_MODE ? demoDashboard : null);
  const [strategies, setStrategies] = useState(DEMO_MODE ? demoStrategies : { primary: [], secondary: [], secondaryCount: 0 });
  const [device, setDevice] = useState(null);
  const [auth, setAuth] = useState({ checked: false, required: false, user: null });
  const [login, setLogin] = useState({ loading: false, error: "" });
  const [passwordDialog, setPasswordDialog] = useState(false);
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
    const onUnauthorized = () => {
      setBackendError("");
      setLogin({ loading: false, error: "会话已过期，请重新登录" });
      setAuth((current) => (current.required && current.user ? { checked: true, required: true, user: null } : current));
    };
    addEventListener("egresscope:unauthorized", onUnauthorized);
    return () => removeEventListener("egresscope:unauthorized", onUnauthorized);
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

  const refreshStrategies = async (payload) => {
    if (payload) { setStrategies(payload); return; }
    try { setStrategies(await api.strategies()); }
    catch { /* Keep the last strategy snapshot; the caller already reported the selection result. */ }
  };
  const visiblePage = canOpenPage(page, auth.user) ? page : "dashboard";
  const title = device ? "设备分析" : PAGE_TITLES[visiblePage];
  const navigatePage = (next, section) => {
    const target = canOpenPage(normalizePage(next), auth.user) ? normalizePage(next) : "dashboard";
    const url = new URL(location.href);
    if (url.searchParams.get("page") !== target || Boolean(section) !== url.searchParams.has("section")) {
      url.searchParams.set("page", target);
      if (section) url.searchParams.set("section", section);
      else url.searchParams.delete("section");
      history.pushState(null, "", url);
    }
    setDevice(null);
    setPage(target);
  };

  useEffect(() => {
    const url = new URL(location.href);
    url.searchParams.set("page", visiblePage);
    history.replaceState(null, "", url);
  }, [visiblePage]);

  useEffect(() => {
    const restoreRoute = () => {
      setDevice(null);
      setPage(normalizePage(new URLSearchParams(location.search).get("page")));
    };
    addEventListener("popstate", restoreRoute);
    return () => removeEventListener("popstate", restoreRoute);
  }, []);

  if (!auth.checked) return <main className="login-screen" />;
  if (backendError && !auth.user && !login.error) return <ServiceUnavailable message={backendError} retry={() => location.reload()} />;
  if (auth.required && !auth.user) return <LoginScreen onLogin={doLogin} {...login} />;
  if (!dashboard) {
    if (backendError) return <ServiceUnavailable message={backendError} retry={() => location.reload()} />;
    return <main className="login-screen"><div className="boot-loading" role="status">正在加载</div></main>;
  }

  return (
    <div className="app-shell">
      <Sidebar page={visiblePage} setPage={navigatePage} collapsed={collapsed} setCollapsed={setCollapsed} online={dashboard.status.online} theme={theme} setTheme={setTheme} onAccount={() => setPasswordDialog(true)} onLogout={doLogout} user={auth.user} />
      <div className="main-shell">
        <Topbar title={title} online={dashboard.status.online} theme={theme} setTheme={setTheme} onAccount={() => setPasswordDialog(true)} onLogout={doLogout} user={auth.user} />
        <main className="main-content">
          {backendError && <div className="inline-message is-error"><WarningCircle />数据刷新失败：{backendError}</div>}
          <PageRenderer
            page={visiblePage}
            device={device}
            devicePage={<DeviceFlow device={device} onBack={() => setDevice(null)} />}
            pages={{
              dashboard: <Dashboard data={dashboard} strategies={strategies} onDevice={selectDevice} onNavigate={navigatePage} canManage={auth.user?.role === "admin"} />,
              connections: <ConnectionsPage data={dashboard} onDevice={selectDevice} canManage={auth.user?.role === "admin"} />,
              audit: <AuditPage data={dashboard} canManage={auth.user?.role === "admin"} />,
              strategies: <StrategiesPage strategies={strategies} onChanged={refreshStrategies} canManage />,
              rules: <RulesPage canManage />,
              subscriptions: <SubscriptionsPage user={auth.user} onStrategiesChanged={refreshStrategies} />,
              gateway: <GatewayPage canManage />,
              users: <UsersPage demoMode={DEMO_MODE} />,
            }}
          />
        </main>
      </div>
      {passwordDialog && <ChangePasswordDialog username={auth.user?.username} demoMode={DEMO_MODE} onClose={() => setPasswordDialog(false)} />}
    </div>
  );
}
