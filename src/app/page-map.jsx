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

export const PAGE_TITLES = {
  dashboard: "状态概览",
  connections: "连接统计",
  audit: "流量分析",
  strategies: "分流策略",
  rules: "规则管理",
  subscriptions: "订阅管理",
  gateway: "网关设置",
  users: "用户管理",
};

export const pageDefinition = page => PAGE_MAP.find(item => item.id === page);
export const canOpenPage = (page, user) => user?.role === "admin" || Boolean(pageDefinition(page)?.viewer);
export const visiblePages = user => PAGE_MAP.filter(item => user?.role === "admin" || item.viewer);
