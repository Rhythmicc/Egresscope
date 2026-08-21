# 订阅生命周期设计（一次性链接）

## 背景

多数供应商的订阅链接是一次性令牌（几分钟内有效），无法轮询。订阅应作为「一次性快照」
管理；供应健康靠消费侧信号推断，而不是重新下载。

## 数据模型

`subscriptions` 表新增两列（migration v15）：

- `url_repeatable INTEGER NOT NULL DEFAULT 0` —— 0 = 一次性（默认），1 = 可重复访问
- `consumed_at INTEGER` —— 一次性链接最近成功拉取的时间戳

已有的 `usage_json` 继续保存 `subscription-userinfo` 响应头里的 `upload/download/total/expire`
快照（G94Cloud 头含 `expire`，Amy 系仅含 `total`）。

## 行为

- **一次性（`url_repeatable = 0`）**：导入时拉取一次；之后绝不自动轮询。「刷新」= 从供应商
  拿新链接重新导入（替换节点快照，规则顺序/策略拓扑/轮换偏好保留）。
- **可重复（`url_repeatable = 1`）**：保留现有自动刷新（`interval` + `enabled`）。
- 自动刷新候选 `due()` 增加 `AND url_repeatable = 1`。
- `refresh()` 成功后写 `consumed_at`。

## 供应健康（免轮询，消费侧推断）

| 想知道 | 来源 |
|---|---|
| 配额余量 | `usage.total` 快照 − 我们的月度记账（`usage_balance` 已算） |
| 到期 | `usage.expire` 快照（静态） |
| 节点存活 | mihomo 健康检查 + 出口探测 |
| 上游已换配置 | 订阅节点从健康 → 集体测速失败 → 提示「请重新获取订阅链接」（后续补） |

## UI

- 编辑弹窗：增加「链接类型」toggle（一次性 / 可重复）；一次性时隐藏「自动刷新 / 刷新周期」，
  并标注「一次性链接，导入后不自动刷新」。
- 订阅卡片：一次性链接且已拉取 → 显示「一次性链接（已消费）」状态。
- 「自动刷新」计数只统计 `enabled && urlRepeatable` 的订阅。

## 不做（本次范围外）

- 不改造 `enabled`（激活/交付）与自动刷新的耦合。

## 已实现（后续补充）

- 「批量失效告警」：`_subscription_health_monitor` 每 120s 检查在用的订阅（网关组合里的），
  某订阅节点连续两轮全部失效（mihomo `alive` 全 false）→ 记一条 warning 事件，提示重新获取订阅链接。
- 事件日志扩展：轮换决策（自动 + 手动）、出口探测结果、订阅刷新成功/失败，均记入 `gateway_events`。
