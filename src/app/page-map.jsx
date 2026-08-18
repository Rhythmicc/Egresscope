import {
  ArrowsDownUp,
  CloudArrowDown,
  Gauge,
  Gear,
  ListMagnifyingGlass,
  PlugsConnected,
  SlidersHorizontal,
  WifiHigh,
} from "@phosphor-icons/react";

export const PAGE_SECTIONS = {
  observe: "观测",
  control: "控制",
  manage: "管理",
};

export const PAGE_MAP = [
  { id: "dashboard", label: "状态概览", section: "observe", icon: Gauge, viewer: true },
  { id: "connections", label: "连接统计", section: "observe", icon: PlugsConnected, viewer: true },
  { id: "audit", label: "流量分析", section: "observe", icon: ListMagnifyingGlass, viewer: true },
  { id: "strategies", label: "分流策略", section: "control", icon: ArrowsDownUp },
  { id: "rules", label: "规则管理", section: "control", icon: SlidersHorizontal },
  { id: "subscriptions", label: "订阅管理", section: "manage", icon: CloudArrowDown, viewer: true },
  { id: "gateway", label: "网关设置", section: "manage", icon: WifiHigh },
  { id: "users", label: "用户管理", section: "manage", icon: Gear },
];

export const PAGE_TITLES = Object.fromEntries(PAGE_MAP.map(item => [item.id, item.label]));

export const pageDefinition = page => PAGE_MAP.find(item => item.id === page);
export const canOpenPage = (page, user) => user?.role === "admin" || Boolean(pageDefinition(page)?.viewer);
export const visiblePages = user => PAGE_MAP.filter(item => user?.role === "admin" || item.viewer);
