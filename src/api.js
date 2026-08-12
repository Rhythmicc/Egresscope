const request = async (path, options = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
      signal: options.signal || controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const error = new Error(body.detail || `请求失败（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("控制面响应超时");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
};

export const api = {
  session: () => request("/api/auth/session"),
  login: (username, password) => request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  users: () => request("/api/users"),
  createUser: (payload) => request("/api/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id, payload) => request(`/api/users/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  subscriptions: () => request("/api/subscriptions"),
  createSubscription: (payload) => request("/api/subscriptions", { method: "POST", body: JSON.stringify(payload) }),
  updateSubscription: (id, payload) => request(`/api/subscriptions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteSubscription: (id) => request(`/api/subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  refreshSubscription: (id) => request(`/api/subscriptions/${encodeURIComponent(id)}/refresh`, { method: "POST" }),
  activateSubscription: (id) => request(`/api/subscriptions/${encodeURIComponent(id)}/activate`, { method: "POST" }),
  deactivateSubscription: (id) => request(`/api/subscriptions/${encodeURIComponent(id)}/deactivate`, { method: "POST" }),
  rotateSubscriptionToken: (id) => request(`/api/subscriptions/${encodeURIComponent(id)}/rotate-token`, { method: "POST" }),
  dashboard: (range = "live") => request(`/api/dashboard?range=${encodeURIComponent(range)}`),
  strategies: () => request("/api/strategies"),
  selectStrategy: (group, name, reconnect = true) => request(`/api/strategies/${encodeURIComponent(group)}`, { method: "PUT", body: JSON.stringify({ name, reconnect }) }),
  ruleWorkspace: () => request("/api/rules/workspace"),
  resetRules: () => request("/api/rules/reset", { method: "POST" }),
  applyRules: () => request("/api/rules/apply", { method: "POST" }),
  createRuleSet: (payload) => request("/api/rules/rule-sets", { method: "POST", body: JSON.stringify(payload) }),
  updateRuleSet: (id, payload) => request(`/api/rules/rule-sets/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteRuleSet: (id) => request(`/api/rules/rule-sets/${encodeURIComponent(id)}`, { method: "DELETE" }),
  moveRuleSet: (id, direction) => request(`/api/rules/rule-sets/${encodeURIComponent(id)}/move`, { method: "POST", body: JSON.stringify({ direction }) }),
  refreshRuleSet: (id) => request(`/api/rules/rule-sets/${encodeURIComponent(id)}/refresh`, { method: "POST" }),
  createCustomRule: (payload) => request("/api/rules/custom", { method: "POST", body: JSON.stringify(payload) }),
  updateCustomRule: (id, payload) => request(`/api/rules/custom/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteCustomRule: (id) => request(`/api/rules/custom/${encodeURIComponent(id)}`, { method: "DELETE" }),
  closeConnection: (id) => request(`/api/connections/${encodeURIComponent(id)}`, { method: "DELETE" }),
  closeAllConnections: () => request("/api/connections", { method: "DELETE" }),
  connectionStatistics: (range = "24h", status = "active", limit = 500, offset = 0) => {
    const query = new URLSearchParams({ range, status, limit: String(limit), offset: String(offset) });
    return request(`/api/connection-statistics?${query}`);
  },
  deviceAliases: () => request("/api/device-aliases"),
  saveDeviceAliases: (aliases) => request("/api/device-aliases", { method: "PUT", body: JSON.stringify({ aliases }) }),
  trafficAnalysis: ({ range, device, groupBy, metric, service, attributionPeriod }) => {
    const query = new URLSearchParams({ range, groupBy, metric });
    if (device) query.set("device", device);
    if (service) query.set("service", service);
    if (attributionPeriod) query.set("attributionPeriod", attributionPeriod);
    return request(`/api/traffic-analysis?${query}`);
  },
  trafficHistory: () => request("/api/traffic-history"),
  device: (ip, range = "live") => request(`/api/devices/${encodeURIComponent(ip)}?range=${encodeURIComponent(range)}`),
};

export const subscribeLive = (onData, onError = () => {}) => {
  let stopped = false;
  let timer;
  const poll = async () => {
    try { onData(await api.dashboard()); } catch (error) { onError(error); }
    if (!stopped) timer = setTimeout(poll, 3000);
  };
  timer = setTimeout(poll, 3000);
  return () => { stopped = true; clearTimeout(timer); };
};
