const now = Date.now();
const timeline = Array.from({ length: 36 }, (_, i) => ({
  time: new Date(now - (35 - i) * 20_000).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  down: 8_000_000 + Math.sin(i / 3) * 4_000_000 + (i > 20 && i < 25 ? 13_000_000 : 0) + (i % 7) * 330_000,
  up: 800_000 + Math.cos(i / 4) * 420_000 + (i > 12 && i < 17 ? 2_300_000 : 0),
}));

const connectionSeeds = [
  ["c1", "macbook-lian", "192.168.31.28", "github.com", "140.82.114.4", 443, "tcp", "GitHub", ["节点选择", "美国", "美国最佳", "us-lax-03"], 512000, 5200000, "00:12:47"],
  ["c2", "macbook-lian", "192.168.31.28", "dl.google.com", "142.250.72.142", 443, "tcp", "Google 直连", ["节点选择", "美国", "美国最佳", "us-lax-03"], 1300000, 18700000, "00:03:21"],
  ["c3", "nas-storage", "192.168.31.190", "s3.us-west-2.amazonaws.com", "52.92.28.23", 443, "tcp", "AWS S3", ["节点选择", "美国", "美国均衡", "us-sea-01"], 8600000, 82300000, "02:14:33"],
  ["c4", "tv-livingroom", "192.168.31.46", "api.netflix.com", "52.16.163.170", 443, "tcp", "Netflix", ["节点选择", "香港", "香港最佳", "hk-hkg-01"], 256000, 12100000, "01:07:58"],
  ["c5", "iphone-14-pro", "192.168.31.77", "appleid.apple.com", "17.253.144.10", 443, "tcp", "Apple 服务", ["节点选择", "美国", "美国均衡", "us-sjc-02"], 320000, 1600000, "00:08:14"],
  ["c6", "pc-gaming", "192.168.31.120", "steamcommunity.com", "146.66.152.18", 443, "tcp", "Steam 社区", ["节点选择", "美国", "美国均衡", "us-sea-01"], 640000, 6800000, "00:16:22"],
  ["c7", "nas-storage", "192.168.31.190", "registry-1.docker.io", "54.198.86.24", 443, "tcp", "Docker", ["节点选择", "美国", "美国最佳", "us-lax-03"], 980000, 14800000, "00:04:51"],
  ["c8", "ipad-studio", "192.168.31.81", "www.youtube.com", "142.250.72.206", 443, "udp", "YouTube", ["节点选择", "日本", "日本最佳", "jp-nrt-01"], 760000, 21600000, "00:21:08"],
];
const connections = Array.from({ length: 5 }, (_, batch) => connectionSeeds.map(
  ([id, device, sourceIP, host, destinationIP, destinationPort, network, rule, chain, upRate, downRate, duration], index) => ({
    id: `${id}-${batch}`,
    device,
    sourceIP,
    host,
    destinationIP,
    destinationPort,
    network: batch % 3 === 2 && destinationPort === 443 ? "udp" : network,
    rule,
    ruleType: "RULE-SET",
    rulePayload: `demo-${rule}`,
    ruleSource: "rule-set",
    ruleSourceLabel: "规则集",
    chain,
    upRate: Math.round(upRate * (1 - batch * .08)),
    downRate: Math.round(downRate * (1 - batch * .06)),
    upload: Math.round(upRate * (85 + batch * 40 + index * 9)),
    download: Math.round(downRate * (85 + batch * 40 + index * 9)),
    duration: batch ? `00:${String(batch * 7 + index).padStart(2,"0")}:${String(12 + index * 3).padStart(2,"0")}` : duration,
  }),
)).flat();

export const demoDashboard = {
  status: { online: true, version: "mihomo v1.19.29", uptime: "7 天 3 小时" },
  totals: { active: 326, upRate: 18_400_000, downRate: 142_700_000, today: 286 * 1024 ** 3, dayChange: 8.2, month: 2.84 * 1024 ** 4, previousMonth: 2.55 * 1024 ** 4, monthChange: 11.6 },
  timeline,
  timelineRange: "live",
  timelineBucketSeconds: 10,
  timelineSummary: { up: 36 * 8_000_000, down: 36 * 32_000_000, traffic: 36 * 40_000_000 },
  devices: [
    { name: "nas-storage", ip: "192.168.31.190", active: 84, up: 8_600_000, down: 82_300_000, total: 122 * 1024 ** 3 },
    { name: "macbook-lian", ip: "192.168.31.28", active: 26, up: 1_860_000, down: 23_900_000, total: 64.8 * 1024 ** 3 },
    { name: "tv-livingroom", ip: "192.168.31.46", active: 18, up: 256_000, down: 12_100_000, total: 38.2 * 1024 ** 3 },
    { name: "ipad-studio", ip: "192.168.31.81", active: 15, up: 760_000, down: 21_600_000, total: 25.1 * 1024 ** 3 },
    { name: "pc-gaming", ip: "192.168.31.120", active: 21, up: 640_000, down: 6_800_000, total: 18.4 * 1024 ** 3 },
  ],
  chains: [
    { name: "美国链路", value: 142 * 1024 ** 3, percent: 49.7 },
    { name: "香港链路", value: 72 * 1024 ** 3, percent: 25.2 },
    { name: "日本链路", value: 41 * 1024 ** 3, percent: 14.3 },
    { name: "DIRECT", value: 24 * 1024 ** 3, percent: 8.4 },
    { name: "其他", value: 7 * 1024 ** 3, percent: 2.4 },
  ],
  connections,
};

export const demoStrategies = {
  primary: [
    { id: "节点选择", name: "节点选择", type: "Selector", typeLabel: "入口策略", modeLabel: "手动选择", selectable: true, now: "美国", nowId: "美国", members: [{ id: "美国", name: "美国" }, { id: "DIRECT", name: "DIRECT" }], delay: "184 ms", delayLevel: "good", children: [] },
    { id: "手动选择", name: "手动选择", type: "Selector", typeLabel: "手动指定", modeLabel: "手动选择", selectable: true, now: "us-lax-03", nowId: "us-lax-03", members: [{ id: "us-lax-03", name: "us-lax-03" }, { id: "DIRECT", name: "DIRECT" }], delay: "184 ms", delayLevel: "good", children: [] },
    { id: "美国", name: "美国", type: "Selector", typeLabel: "地区策略", modeLabel: "手动选择", selectable: true, now: "🇺🇸 美国最佳", nowId: "美国最佳", members: [{ id: "美国最佳", name: "🇺🇸 美国最佳" }, { id: "美国均衡", name: "🇺🇸 美国均衡" }], delay: "184 ms", delayLevel: "good", children: [{ id: "美国最佳", name: "美国最佳", type: "URLTest", modeLabel: "自动测速", selectable: false, now: "🇺🇸 [电信] 美国洛杉矶 国际专线", health: { available: 2, total: 2 }, members: [{ id: "us-lax-03", name: "🇺🇸 [电信] 美国洛杉矶 国际专线", alive: true, selected: true, delay: "184 ms", delayLevel: "good" }, { id: "us-sjc-02", name: "🇺🇸 [联通] 美国圣何塞 国际专线", alive: true, selected: false, delay: "276 ms", delayLevel: "good" }], delay: "184 ms", delayLevel: "good" }, { id: "美国均衡", name: "美国均衡", type: "LoadBalance", modeLabel: "自动均衡", selectable: false, now: "自动均衡", health: { available: 2, total: 2 }, members: [{ id: "us-lax-03", name: "🇺🇸 [电信] 美国洛杉矶 国际专线", alive: true, selected: false, delay: "184 ms", delayLevel: "good" }, { id: "us-sjc-02", name: "🇺🇸 [联通] 美国圣何塞 国际专线", alive: true, selected: false, delay: "276 ms", delayLevel: "good" }], delay: "184 ms", delayLevel: "good" }] },
    { id: "香港", name: "香港", type: "Selector", typeLabel: "地区策略", modeLabel: "手动选择", selectable: true, now: "香港最佳", nowId: "香港最佳", members: [{ id: "香港最佳", name: "香港最佳" }, { id: "香港均衡", name: "香港均衡" }], delay: "555 ms", delayLevel: "fair", children: [{ id: "香港最佳", name: "香港最佳", type: "URLTest", modeLabel: "自动测速", selectable: false, now: "[电信] 香港 特区专线", health: { available: 2, total: 2 }, members: [{ id: "hk-hkg-01", name: "[电信] 香港 特区专线", alive: true, selected: true, delay: "555 ms", delayLevel: "fair" }, { id: "hk-hkg-02", name: "[联通] 香港 特区专线", alive: true, selected: false, delay: "682 ms", delayLevel: "fair" }], delay: "555 ms", delayLevel: "fair" }, { id: "香港均衡", name: "香港均衡", type: "LoadBalance", modeLabel: "自动均衡", selectable: false, now: "自动均衡", health: { available: 2, total: 2 }, members: [{ id: "hk-hkg-01", name: "[电信] 香港 特区专线", alive: true, selected: false, delay: "555 ms", delayLevel: "fair" }, { id: "hk-hkg-02", name: "[联通] 香港 特区专线", alive: true, selected: false, delay: "682 ms", delayLevel: "fair" }], delay: "555 ms", delayLevel: "fair" }] },
    { id: "日本", name: "日本", type: "Selector", typeLabel: "地区策略", modeLabel: "手动选择", selectable: true, now: "日本最佳", nowId: "日本最佳", members: [{ id: "日本最佳", name: "日本最佳" }, { id: "日本均衡", name: "日本均衡" }], delay: "717 ms", delayLevel: "fair", children: [{ id: "日本最佳", name: "日本最佳", type: "URLTest", modeLabel: "自动测速", selectable: false, now: "[电信] 日本东京 国际专线", health: { available: 2, total: 2 }, members: [{ id: "jp-nrt-01", name: "[电信] 日本东京 国际专线", alive: true, selected: true, delay: "717 ms", delayLevel: "fair" }, { id: "jp-kix-02", name: "[联通] 日本东京 国际专线", alive: true, selected: false, delay: "832 ms", delayLevel: "slow" }], delay: "717 ms", delayLevel: "fair" }, { id: "日本均衡", name: "日本均衡", type: "LoadBalance", modeLabel: "自动均衡", selectable: false, now: "自动均衡", health: { available: 2, total: 2 }, members: [{ id: "jp-nrt-01", name: "[电信] 日本东京 国际专线", alive: true, selected: false, delay: "717 ms", delayLevel: "fair" }, { id: "jp-kix-02", name: "[联通] 日本东京 国际专线", alive: true, selected: false, delay: "832 ms", delayLevel: "slow" }], delay: "717 ms", delayLevel: "fair" }] },
  ],
  secondary: ["微软Bing", "微软云盘", "苹果服务", "奈飞视频", "游戏平台", "国外媒体", "应用净化", "全球直连", "漏网之鱼"].map(name => ({ name, now: name === "全球直连" ? "DIRECT" : "节点选择" })),
  secondaryCount: 18,
};

export const demoDevice = {
  name: "macbook-lian", ip: "192.168.31.28", vendor: "Apple", active: 26, up: 1_860_000, down: 23_900_000,
  timeline: timeline.map((item, i) => ({ ...item, down: item.down * (0.14 + (i % 5) * .01), up: item.up * .22 })),
  timelineBucketSeconds: 10,
  rangeSummary: { up: 286_000_000, down: 1_420_000_000, traffic: 1_706_000_000 },
  destinations: [
    { host: "dl.google.com", rule: "Google 直连", rate: 18_700_000, up: 42_000_000, down: 1_460_000_000, traffic: 1_502_000_000 },
    { host: "github.com", rule: "GitHub", rate: 5_200_000, up: 18_000_000, down: 326_000_000, traffic: 344_000_000 },
    { host: "appleid.apple.com", rule: "Apple 服务", rate: 1_600_000, up: 7_200_000, down: 86_000_000, traffic: 93_200_000 },
    { host: "ocsp.apple.com", rule: "Apple 服务", rate: 420_000, up: 1_800_000, down: 21_000_000, traffic: 22_800_000 },
  ],
  flow: {
    nodes: ["macbook-lian", "Google 直连", "GitHub", "漏网之鱼", "节点选择", "美国", "美国最佳", "美国均衡", "us-lax-03", "us-sjc-02", "DIRECT"].map(name => ({ name })),
    links: [
      { source: 0, target: 1, value: 18_700_000 }, { source: 0, target: 2, value: 5_200_000 }, { source: 0, target: 3, value: 1_200_000 },
      { source: 1, target: 4, value: 18_700_000 }, { source: 2, target: 4, value: 5_200_000 }, { source: 3, target: 4, value: 1_200_000 },
      { source: 4, target: 5, value: 23_200_000 }, { source: 4, target: 10, value: 1_900_000 },
      { source: 5, target: 6, value: 19_100_000 }, { source: 5, target: 7, value: 4_100_000 },
      { source: 6, target: 8, value: 19_100_000 }, { source: 7, target: 9, value: 4_100_000 },
    ],
  },
};
