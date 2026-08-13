import { useEffect, useMemo, useState } from "react";
import {
  AppleLogo,
  ArrowRight,
  ClockCounterClockwise,
  Desktop,
  GithubLogo,
  Globe,
  GoogleLogo,
  MagnifyingGlass,
  OpenAiLogo,
  Plus,
  ShieldCheck,
  SlidersHorizontal,
  TelegramLogo,
  WarningCircle,
  WindowsLogo,
  XLogo,
  YoutubeLogo,
} from "@phosphor-icons/react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../../api";
import { bytes, connectionDuration, connectionTime } from "../../lib/formatters";
import { QuickRuleModal } from "./ConnectionsPage";
import { DASHBOARD_RANGES } from "./DashboardPage";

const DEMO_MODE = import.meta.env.DEV || import.meta.env.VITE_DEMO_MODE === "true";

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

const DEMO_LEDGER_EVENTS = [
  { id:"ledger-1",status:"ended",device:"U55C",sourceIP:"192.168.31.42",service:"Hugging Face",host:"cdn-lfs.huggingface.co",destinationIP:"13.33.88.71",destinationPort:"443",network:"tcp",route:"proxy",rule:"AI 模型下载",ruleType:"RULE-SET",rulePayload:"ssslab-ai-models",ruleSource:"rule-set",ruleSourceLabel:"规则集",chain:["节点选择","美国","美国最佳","🇺🇸 电信 美国洛杉矶 04"],policy:"美国最佳",node:"🇺🇸 电信 美国洛杉矶 04",startedAt:1786591200,endedAt:1786593120,durationSeconds:1920,upload:42000000,download:2.6*1024**3,traffic:2.6*1024**3+42000000 },
  { id:"ledger-2",status:"ended",device:"ssslab-login-1",sourceIP:"192.168.31.225",service:"Matrix",host:"matrix-client.matrix.org",destinationIP:"104.22.5.18",destinationPort:"443",network:"tcp",route:"proxy",rule:"最终兜底",ruleType:"MATCH",rulePayload:"",ruleSource:"fallback",ruleSourceLabel:"安全兜底",chain:["节点选择","香港","香港智能","🇭🇰 香港 03"],policy:"香港智能",node:"🇭🇰 香港 03",startedAt:1786586100,endedAt:1786590300,durationSeconds:4200,upload:80000000,download:.9*1024**3,traffic:.9*1024**3+80000000 },
  { id:"ledger-3",status:"active",device:"192.168.31.177",sourceIP:"192.168.31.177",service:"Microsoft",host:"download.visualstudio.microsoft.com",destinationIP:"23.44.18.91",destinationPort:"443",network:"tcp",route:"proxy",rule:"Microsoft",ruleType:"RULE-SET",rulePayload:"ssslab-microsoft",ruleSource:"rule-set",ruleSourceLabel:"规则集",chain:["节点选择","美国","美国智能","🇺🇸 联通 美国西雅图 07"],policy:"美国智能",node:"🇺🇸 联通 美国西雅图 07",startedAt:1786593300,endedAt:null,durationSeconds:940,upload:18000000,download:.45*1024**3,traffic:.45*1024**3+18000000 },
  { id:"ledger-direct",status:"ended",device:"U55C",sourceIP:"192.168.31.42",service:"Ssslab",host:"a100.ssslab.cn",destinationIP:"10.18.18.244",destinationPort:"22",network:"tcp",route:"direct",rule:"实验室内网",ruleType:"IP-CIDR",rulePayload:"10.0.0.0/8",ruleSource:"custom",ruleSourceLabel:"自定义规则",chain:["全球直连","DIRECT"],policy:"DIRECT",node:"DIRECT",startedAt:1786592200,endedAt:1786592500,durationSeconds:300,upload:65000000,download:220000000,traffic:285000000 },
];

const DEMO_ANOMALIES = {
  count: 2,
  canManage: true,
  ai: { configured: true, providerLabel: "DeepSeek", model: "deepseek-v4-flash" },
  settings: { enabled: true, autonomous: true, thresholdBytes: 5 * 1024 ** 3, windowSeconds: 300, actionPolicy: "ai", cooldownSeconds: 3600, protectedTargets: ["router.local"] },
  actions: [
    { id: 1, device: "U55C", host: "cdn-lfs.huggingface.co", traffic: 6.4 * 1024 ** 3, decision: "direct", status: "executed", reason: "可信模型文件下载，已改走直连", ruleContent: "DOMAIN,cdn-lfs.huggingface.co,DIRECT", createdAt: 1786593600 },
    { id: 2, device: "192.168.31.177", host: "unknown-pool.example", traffic: 5.7 * 1024 ** 3, decision: "block", status: "executed", reason: "持续高流量且目标无法归类", ruleContent: "DOMAIN,unknown-pool.example,REJECT", createdAt: 1786589200 },
  ],
};

const demoLedger = (route = "proxy") => {
  const events = DEMO_LEDGER_EVENTS.filter(item => route === "all" || item.route === route);
  const upload = events.reduce((sum,item)=>sum+item.upload,0);
  const download = events.reduce((sum,item)=>sum+item.download,0);
  return { retentionDays:30, precision:{ unit:"connection",target:"host-or-ip",urlPathAvailable:false }, summary:{ events:events.length,devices:new Set(events.map(item=>item.sourceIP)).size,upload,download,traffic:upload+download }, events };
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

function TrafficLedger({ ledger, route, setRoute, order, setOrder, query, setQuery, canManage, onAddRule }) {
  const events = useMemo(() => (ledger.events || []).filter(event => `${event.device} ${event.sourceIP} ${event.host} ${event.destinationIP} ${event.rule} ${event.chain?.join(" ")}`.toLowerCase().includes(query.toLowerCase())), [ledger.events, query]);
  return <section className="proxy-ledger panel">
    <div className="proxy-ledger-head">
      <div><h3>代理花费追踪</h3><strong>{bytes(ledger.summary?.traffic || 0)}</strong><span>{ledger.summary?.events || 0} 个连接事件</span></div>
      <div className="ledger-controls"><div className="analysis-toggle"><button className={route==="proxy"?"active":""} onClick={()=>setRoute("proxy")}>代理出口</button><button className={route==="direct"?"active":""} onClick={()=>setRoute("direct")}>直连对照</button></div><div className="analysis-toggle"><button className={order==="traffic"?"active":""} onClick={()=>setOrder("traffic")}>流量优先</button><button className={order==="recent"?"active":""} onClick={()=>setOrder("recent")}>最近发生</button></div></div>
    </div>
    <div className="ledger-search"><MagnifyingGlass/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索设备、目标、规则、策略或节点"/></div>
    <div className="ledger-table-wrap"><div className="ledger-table-head"><span>流量</span><span>时间 / 设备</span><span>访问目标</span><span>命中规则</span><span>策略与出口节点</span><span>调整</span></div>
      <div className="ledger-event-list">{events.length ? events.map(event=><article className={`ledger-event route-${event.route}`} key={event.id}>
        <div className="ledger-traffic"><strong>{bytes(event.traffic)}</strong><span>↓ {bytes(event.download)} · ↑ {bytes(event.upload)}</span></div>
        <div className="ledger-origin"><time>{connectionTime(event.startedAt)}</time><span><Desktop/>{event.device}</span><small>{event.status==="active"?"进行中":connectionDuration(event.durationSeconds)}</small></div>
        <div className="ledger-target"><strong>{event.host || event.destinationIP}</strong><span>{event.service} · {event.destinationIP}:{event.destinationPort}</span></div>
        <div className="ledger-rule"><strong>{event.rule}</strong><span>{event.ruleSourceLabel || "规则"}</span></div>
        <div className="ledger-exit"><span className={`route-badge ${event.route}`}>{event.route==="direct"?"DIRECT":"PROXY"}</span><strong>{event.policy || "未识别策略"}</strong>{event.route==="proxy"&&<><ArrowRight/><span title={event.node}>{event.node || "节点未知"}</span></>}</div>
        <div className="ledger-action">{canManage?<button onClick={()=>onAddRule(event)}><Plus/>改规则</button>:<span>只读</span>}</div>
      </article>) : <div className="ledger-empty">当前筛选条件下没有可追溯的流量事件</div>}</div>
    </div>
  </section>;
}

const anomalyDecision = decision => ({ block:"阻断", direct:"改走直连", alert:"仅提醒" }[decision] || "仅提醒");
const anomalyStatus = status => ({ analyzing:"分析中", alerted:"待处理", executed:"已处置", skipped:"已跳过", failed:"失败" }[status] || status);

function AnomalyGuard({ data, canManage, onEdit }) {
  const latest = data.actions?.[0];
  const settings = data.settings || {};
  return <section className={`anomaly-guard panel ${settings.autonomous ? "is-armed" : ""}`}>
    <div className="anomaly-identity"><span className="anomaly-icon"><ShieldCheck weight="fill" /></span><div><h3>异常守卫</h3><strong>{settings.enabled ? settings.autonomous ? "自动处置已启用" : "监测中 · 等待确认" : "已暂停"}</strong></div></div>
    <div className="anomaly-threshold"><span>{Math.round((settings.windowSeconds || 300) / 60)} 分钟同目标阈值</span><strong>{bytes(settings.thresholdBytes || 0)}</strong></div>
    <div className="anomaly-policy"><span>处置方式</span><strong>{settings.actionPolicy === "ai" ? `${data.ai?.providerLabel || "AI"} 决策` : anomalyDecision(settings.actionPolicy)}</strong></div>
    <div className="anomaly-latest">{latest ? <><span className={`anomaly-state ${latest.status}`}>{anomalyStatus(latest.status)}</span><strong>{latest.device} · {latest.host || latest.destinationIP}</strong><small>{bytes(latest.traffic)} · {anomalyDecision(latest.decision)}</small></> : <strong>尚未发现高流量连接</strong>}</div>
    {canManage && <button className="anomaly-settings-button" onClick={onEdit}><SlidersHorizontal />设置</button>}
  </section>;
}

function AnomalySettingsModal({ editor, setEditor, onSave }) {
  if (!editor) return null;
  return <div className="modal-backdrop" onMouseDown={()=>setEditor(null)}><form className="user-modal anomaly-modal" onMouseDown={event=>event.stopPropagation()} onSubmit={event=>{event.preventDefault();onSave(editor);}}>
    <div className="modal-heading"><div><span className="eyebrow">异常守卫</span><h3>高流量自动处置</h3></div><button type="button" onClick={()=>setEditor(null)}>×</button></div>
    <div className="anomaly-switches"><label><span><strong>启用异常检测</strong></span><input type="checkbox" checked={editor.enabled} onChange={event=>setEditor({...editor,enabled:event.target.checked})}/></label><label><span><strong>允许自动执行</strong></span><input type="checkbox" checked={editor.autonomous} onChange={event=>setEditor({...editor,autonomous:event.target.checked})}/></label></div>
    <div className="modal-fields"><label>同目标 5 分钟累计阈值（GiB）<input type="number" min="0.1" max="10240" step="0.1" value={editor.thresholdGiB} onChange={event=>setEditor({...editor,thresholdGiB:Number(event.target.value)})}/></label><label>决策方式<select value={editor.actionPolicy} onChange={event=>setEditor({...editor,actionPolicy:event.target.value})}><option value="ai">由 AI 判断</option><option value="alert">仅提醒</option><option value="direct">改走直连</option><option value="block">阻断目标</option></select></label></div>
    <label>同一目标冷却期（分钟）<input type="number" min="5" max="10080" value={editor.cooldownMinutes} onChange={event=>setEditor({...editor,cooldownMinutes:Number(event.target.value)})}/></label>
    <label>保护目标<input value={editor.protectedText} onChange={event=>setEditor({...editor,protectedText:event.target.value})} placeholder="router.local, example.internal"/><small>内网、回环和链路本地地址始终受到保护；此处可追加域名或 IP。</small></label>
    {editor.autonomous && <div className="anomaly-warning"><WarningCircle/>AI 只能在阻断、改走直连、仅提醒中选择；执行时终止该设备到同一目标的全部活动连接。</div>}
    {editor.error && <div className="inline-message is-error">{editor.error}</div>}
    <button className="primary-button modal-submit" disabled={editor.busy}>{editor.busy?"正在保存":"保存守卫策略"}</button>
  </form></div>;
}

export function AuditPage({ data, canManage = false }) {
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
  const [ledgerRoute, setLedgerRoute] = useState("proxy");
  const [ledgerOrder, setLedgerOrder] = useState("traffic");
  const [ledgerQuery, setLedgerQuery] = useState("");
  const [ledger, setLedger] = useState(DEMO_MODE ? demoLedger("proxy") : { summary:{events:0,devices:0,upload:0,download:0,traffic:0}, events:[] });
  const [quickRule, setQuickRule] = useState(null);
  const [anomalies, setAnomalies] = useState(DEMO_MODE ? DEMO_ANOMALIES : { actions:[], settings:{}, ai:{} });
  const [anomalyEditor, setAnomalyEditor] = useState(null);
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
  useEffect(() => { api.trafficAnomalies().then(setAnomalies).catch(error => { if (!DEMO_MODE) setMessage(error.message); }); }, []);
  useEffect(() => {
    const timeout = setTimeout(() => {
      api.trafficLedger({ range:rangeKey,route:ledgerRoute,order:ledgerOrder,device,query:ledgerQuery })
        .then(setLedger)
        .catch(error => { if (DEMO_MODE) setLedger(demoLedger(ledgerRoute)); else setMessage(error.message); });
    }, ledgerQuery ? 220 : 0);
    return () => clearTimeout(timeout);
  }, [rangeKey,device,ledgerRoute,ledgerOrder,ledgerQuery]);
  const openQuickRule = async (event) => {
    const host = event.host && !/^[\d.:]+$/.test(event.host) ? event.host : "";
    const initial = { connection:event, matchType:host?"DOMAIN":"IP-CIDR", value:host||event.destinationIP, policy:"", policies:[], terminateCurrent:event.status === "active", busy:true, error:"" };
    if (DEMO_MODE) {
      const policies = ["节点选择", "美国最佳", "美国智能", "香港最佳", "香港智能", "DIRECT", "REJECT"];
      setQuickRule({ ...initial, policy:event.policy && policies.includes(event.policy) ? event.policy : "节点选择", policies, busy:false });
      return;
    }
    setQuickRule(initial);
    try { const workspace=await api.ruleWorkspace(); const policies=[...new Set([...(workspace.availablePolicies||[]),"DIRECT","REJECT"])]; const policy=event.chain.find(item=>policies.includes(item))||policies.find(item=>item==="节点选择")||policies[0]||"DIRECT"; setQuickRule({...initial,policy,policies,busy:false}); }
    catch(error){ setQuickRule({...initial,policies:["DIRECT","REJECT"],policy:"DIRECT",busy:false,error:error.message}); }
  };
  const saveQuickRule = async editor => {
    setQuickRule({...editor,busy:true,error:""});
    try {
      await api.createCustomRule({content:editor.content,placement:"before",note:`来自流量追踪：${editor.connection.device}`});
      await api.applyRules();
      if (editor.terminateCurrent && editor.connection.status === "active") {
        try { await api.closeConnection(editor.connection.id); setMessage(`规则已应用，当前连接已终止并等待重连：${editor.content}`); }
        catch { setMessage(`规则已应用，但当前连接已结束或未能终止：${editor.content}`); }
      } else setMessage(`规则已应用：${editor.content}`);
      setQuickRule(null);
    }
    catch(error){ setQuickRule({...editor,busy:false,error:error.message}); }
  };
  const editAnomalies = () => { const settings=anomalies.settings||{}; setAnomalyEditor({...settings,thresholdGiB:Math.round((settings.thresholdBytes||5*1024**3)/1024**3*10)/10,cooldownMinutes:Math.round((settings.cooldownSeconds||3600)/60),protectedText:(settings.protectedTargets||[]).join(", "),busy:false,error:""}); };
  const saveAnomalies = async editor => {
    setAnomalyEditor({...editor,busy:true,error:""});
    const payload={enabled:editor.enabled,autonomous:editor.autonomous,thresholdBytes:Math.round(editor.thresholdGiB*1024**3),actionPolicy:editor.actionPolicy,cooldownSeconds:Math.round(editor.cooldownMinutes*60),protectedTargets:editor.protectedText.split(/[,\n]/).map(item=>item.trim()).filter(Boolean)};
    try { const result=DEMO_MODE?{settings:payload}:await api.updateTrafficAnomalySettings(payload); setAnomalies(current=>({...current,settings:result.settings}));setAnomalyEditor(null);setMessage("异常守卫设置已更新"); }
    catch(error){setAnomalyEditor({...editor,busy:false,error:error.message});}
  };
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
    <AnomalyGuard data={anomalies} canManage={canManage} onEdit={editAnomalies}/>
    <TrafficLedger ledger={ledger} route={ledgerRoute} setRoute={setLedgerRoute} order={ledgerOrder} setOrder={setLedgerOrder} query={ledgerQuery} setQuery={setLedgerQuery} canManage={canManage} onAddRule={openQuickRule}/>
    <div className="analysis-workspace">
      <section className="service-ranking panel"><div className="compact-panel-head"><h3>代理服务 / 目标排行</h3><div className="analysis-toggle"><button className={groupBy==="service"?"active":""} onClick={()=>setGroupBy("service")}>服务</button><button className={groupBy==="target"?"active":""} onClick={()=>setGroupBy("target")}>目标</button></div></div><div className="ranking-columns"><div className="ranking-list">{items.slice(0,7).map((item,index)=><button className={selectedItem?.id===item.id?"selected":""} key={item.id} onClick={()=>setSelectedService(item.service || item.name)}><b>{index+1}</b><ServiceIcon type={item.icon}/><span><strong>{serviceDisplayName(item.name)}</strong><em>{item.details?.length || 0} 个主机</em></span><span className="ranking-value"><strong>{bytes(item.traffic)}</strong><em>{item.percent}%</em></span></button>)}</div><div className="host-ranking"><h4>{serviceDisplayName(selectedItem?.name || "服务")} 相关主机</h4>{(selectedItem?.details || []).slice(0,6).map(detail=><div key={detail.host}><code>{detail.host}</code><strong>{bytes(detail.up + detail.down)}</strong></div>)}<div className="host-total"><span>合计</span><strong>{bytes(selectedItem?.traffic || 0)}</strong></div></div></div></section>
      <section className="device-attribution panel"><div className="compact-panel-head"><h3>{attribution.service || selectedItem?.name || "服务"} · 来源设备用量</h3><div className="analysis-toggle">{[["hour","按小时"],["day","按天"],["month","按月"]].map(([id,label])=><button key={id} className={attributionPeriod===id?"active":""} onClick={()=>setAttributionPeriod(id)}>{label}</button>)}</div></div><div className="attribution-body"><div className="attribution-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={attributionChart} margin={{top:12,right:4,left:-10,bottom:0}}><CartesianGrid stroke="var(--grid)" vertical={false}/><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={11}/><YAxis tickFormatter={bytes} tickLine={false} axisLine={false} fontSize={11} width={58}/><Tooltip content={<UsageTooltip/>}/>{attributionDevices.map((entry,index)=><Bar key={entry.ip} dataKey={entry.ip} name={entry.name} stackId="usage" fill={DEVICE_COLORS[index%DEVICE_COLORS.length]} isAnimationActive={false}/>)}</BarChart></ResponsiveContainer></div><div className="device-usage-table"><div className="device-usage-head"><span>设备</span><span>IP 地址</span><span>累计</span><span>占比</span></div>{attributionDevices.map((entry,index)=><div className="device-usage-row" key={entry.ip}><span><i style={{background:DEVICE_COLORS[index%DEVICE_COLORS.length]}}/>{entry.name}</span><code>{entry.ip}</code><strong>{bytes(entry.traffic)}</strong><b>{entry.percent}%</b></div>)}<div className="device-usage-total"><span>合计</span><strong>{bytes(attributionDevices.reduce((sum,item)=>sum+item.traffic,0))}</strong><b>100%</b></div></div></div></section>
    </div>
    <section className="proxy-history panel"><div className="compact-panel-head"><h3>代理流量历史用量</h3><div className="analysis-toggle"><button className={historyPeriod==="month"?"active":""} onClick={()=>setHistoryPeriod("month")}>月度</button><button className={historyPeriod==="year"?"active":""} onClick={()=>setHistoryPeriod("year")}>年度</button></div></div><div className="history-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={historyChart} margin={{top:24,right:12,left:4,bottom:0}}><CartesianGrid stroke="var(--grid)" vertical={false}/><XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={11}/><YAxis tickFormatter={bytes} tickLine={false} axisLine={false} fontSize={11} width={60}/><Tooltip content={<UsageTooltip/>}/><Bar dataKey="down" name="下载" stackId="history" fill="#3f7df0" isAnimationActive={false}/><Bar dataKey="up" name="上传" stackId="history" fill="#a76aeb" radius={[3,3,0,0]} isAnimationActive={false}/></BarChart></ResponsiveContainer></div></section>
    <QuickRuleModal editor={quickRule} setEditor={setQuickRule} onSave={saveQuickRule} contextLabel="流量追踪"/>
    <AnomalySettingsModal editor={anomalyEditor} setEditor={setAnomalyEditor} onSave={saveAnomalies}/>
  </div>;
}
