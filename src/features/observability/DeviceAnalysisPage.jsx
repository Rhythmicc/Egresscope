import { Component, useEffect, useState } from "react";
import {
  CaretDown,
  Funnel,
  GlobeHemisphereEast,
  Pulse,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  ResponsiveContainer,
  Sankey,
  Tooltip,
} from "recharts";
import { api } from "../../api";
import { demoDevice } from "../../demo-data";
import { bucketDuration, bytes, rate } from "../../lib/formatters";
import { DASHBOARD_RANGES, TrafficChart } from "./DashboardPage";

class FlowChartBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(previousProps) {
    if (this.state.failed && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (this.state.failed) {
      return <div className="flow-chart-fallback"><WarningCircle weight="fill" /><strong>流量路径暂时无法绘制</strong><span>其他设备统计仍可正常查看，请稍后刷新。</span></div>;
    }
    return this.props.children;
  }
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

export function DeviceFlow({ device, onBack }) {
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
          <FlowChartBoundary resetKey={flow}>
            <ResponsiveContainer width="100%" height="100%">
              <Sankey data={flow} node={<FlowNode />} nodePadding={28} nodeWidth={8} link={{ stroke: "#4f8df7", strokeOpacity: 0.22 }} margin={{ top: 12, right: 110, bottom: 12, left: 110 }}>
                <Tooltip formatter={(v) => bytes(v)} contentStyle={{ background: "#172033", border: "1px solid #2c3850", borderRadius: 8, color: "#eef4ff" }} />
              </Sankey>
            </ResponsiveContainer>
          </FlowChartBoundary>
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
      </div>
    </div>
  );
}
