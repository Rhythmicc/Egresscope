# Egresscope

Egresscope 是一个面向 mihomo 网关的多用户控制面和持久化流量审计系统。它把
节点来源、请求规则和策略拓扑分开管理，并追踪设备、目标主机、命中规则与实际
出口链路的累计流量。

## 功能

- 状态概览、可滚动的实时连接和单连接终止
- 按设备、服务、目标、策略链和出口节点统计累计流量
- 长期保留日/月/年直连与代理流量汇总，高频明细按策略清理
- 策略切换、受影响连接重连、节点延迟与地区分组
- 有序规则集和自定义规则工作区，校验后热重载 mihomo
- Surge 与 Clash/Mihomo 订阅解析、定时刷新和独立交付链接
- 管理员/普通用户隔离；普通用户只能读取授权设备并管理自己的订阅
- 深浅色主题和 Asia/Shanghai 时间展示

流量统计来自 mihomo 的连接累计计数器。采集器每 2 秒观察连接、每 10 秒将完整
区间增量原子写入 SQLite；连接结束后，目标、规则、链路和累计字节仍可追溯。

## Docker 部署

要求 Linux、Docker Compose、`/dev/net/tun`，以及可用的 mihomo 配置。

```sh
cp .env.example .env
mkdir -p runtime/mihomo runtime/panel
cp deploy/mihomo.example.yaml runtime/mihomo/config.yaml
# 编辑 .env 和 config.yaml，使控制器密钥一致并加入节点、策略和规则
docker compose up -d --build
```

面板监听 `2086`，示例显式混合代理监听 `9999`。生产环境应通过 HTTPS 反向代理
访问面板，防火墙禁止不受信任来源直连 2086，并保持 mihomo 控制器只监听
`127.0.0.1:9090`。若暂时仅能使用 HTTP，必须显式设置
`EGRESSCOPE_SECURE_COOKIE=false`，并把它视为临时降级。

已有 mihomo 实例时，可以只构建和运行 `panel` 服务，将其控制器地址与配置文件
挂载调整为现有路径。旧版 `SSSLAB_*` 环境变量和数据库文件名会被兼容读取，便于
原地升级；新部署应使用 `EGRESSCOPE_*`。

### 必需变量

| 变量 | 说明 |
|---|---|
| `MIHOMO_CONTROLLER_SECRET` | 与 mihomo `secret` 一致；不得把控制器暴露到局域网 |
| `EGRESSCOPE_SESSION_SECRET` | 至少 32 字符的独立随机会话密钥 |
| `EGRESSCOPE_ADMIN_PASSWORD` | 首次启动创建管理员；数据库已有用户后不再使用 |

`EGRESSCOPE_SECURE_COOKIE` 默认 `true`，时区默认 `Asia/Shanghai`，明细保留期默认
14 天。月度和年度汇总不会随明细清理。设备别名格式见 `devices.example.json`。
若 mihomo 配置目录限制了宿主机组权限，将 `MIHOMO_CONFIG_GID` 设为可读取该目录
的 GID；面板只需读取配置，不应获得写权限。

## 开发和验证

```sh
npm ci
npm run dev
python3 -m unittest discover -s tests -v
npm run test:sites
npm run build
npm audit --audit-level=high
docker compose config
```

开发模式可使用演示数据；生产构建不会在后端故障时伪造管理员或审计记录。

## 安全与隐私

订阅地址、交付链接、节点密码和流量数据库都属于敏感信息。请使用加密备份、限制
`runtime/` 的文件权限，并在泄露后从订阅管理中轮换交付链接。反向代理访问日志应
排除 `/sub/` 路径。漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## License

[GNU Affero General Public License v3.0 or later](LICENSE)。网络部署的修改版本也需
向使用者提供对应源代码。
