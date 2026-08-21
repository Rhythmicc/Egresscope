# Egresscope

[![Docker](https://img.shields.io/docker/v/rhythmlian/egresscope?sort=semver&label=Docker)](https://hub.docker.com/r/rhythmlian/egresscope)
[![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20arm64%20%7C%20armv7-4c8bf5)](https://hub.docker.com/r/rhythmlian/egresscope/tags)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

Egresscope 是一个面向 [mihomo](https://github.com/MetaCubeX/mihomo) 网关的多用户控制面与持久化流量审计系统。它将节点来源、分流规则和策略拓扑解耦，并持续记录设备、目标主机、命中规则与真实出口节点的累计流量。

> Egresscope is a self-hosted, multi-user control plane for a mihomo gateway, with durable traffic attribution and responsive Web administration.

## 核心能力

- 状态概览、实时连接、最近 30 天历史会话和单连接终止
- 按设备、服务、目标、规则、策略与出口节点统计累计流量
- 持久化日/月/年流量汇总；服务重启不会清空统计
- 异常流量守卫，可按时间窗口识别并处置高消耗目标
- 策略切换、受影响连接重连、节点延迟测试和地区策略管理
- 有序规则集、自定义覆盖规则、校验后热重载，以及可选 GitHub 同步
- Surge 与 Clash/Mihomo 订阅解析、定时刷新、节点过滤/改名和独立交付链接
- 可选 DeepSeek / OpenRouter 辅助生成节点过滤建议
- 管理员与普通用户隔离；普通用户只读授权设备并管理自己的订阅
- 深浅色主题，以及桌面、平板和手机响应式布局

## 统计边界

Egresscope 从 mihomo 控制器读取连接累计计数器。采集器默认每 2 秒观察连接、每 10 秒将完整区间增量原子写入 SQLite；连接结束后仍可查询目标、规则、出口链路与累计字节。

Egresscope 不是 TLS 中间人或完整 DPI 系统。对加密连接通常可记录主机名或目标 IP、端口和 mihomo 元数据，但不会看到 HTTPS 请求路径、正文或凭据。采集器启用之前发生的流量也无法追溯。

## 快速部署

要求：Linux、Docker Compose、`/dev/net/tun`，以及可用的 mihomo 节点与规则配置。

```sh
git clone https://github.com/Rhythmicc/Egresscope.git
cd Egresscope
cp .env.example .env
mkdir -p runtime/mihomo runtime/panel
cp deploy/mihomo.example.yaml runtime/mihomo/config.yaml

# 生成独立随机密钥；将结果分别写入 .env
openssl rand -hex 32
openssl rand -base64 24

# 编辑 .env 和 runtime/mihomo/config.yaml，使控制器密钥一致
docker compose pull
docker compose up -d
docker compose ps
```

默认服务：

| 服务 | 端口 | 说明 |
| --- | ---: | --- |
| Web 管理面板 | `2086` | 生产环境应置于 HTTPS 反向代理之后 |
| HTTP/SOCKS5 混合代理 | `9999` | 按需通过防火墙或端口映射开放 |
| mihomo 控制器 | `127.0.0.1:9090` | 只应在本机监听，不应暴露到局域网或公网 |

当前固定版本镜像：

```text
rhythmlian/egresscope:0.4.1
rhythmlian/egresscope:0.4
rhythmlian/egresscope:latest
rhythmlian/egresscope:mihomo-1.19.29
```

面板镜像发布 `linux/amd64`、`linux/arm64` 和 `linux/arm/v7`。Compose 默认固定到 `0.4.1`；如需跟随稳定最新版，可在 `.env` 中设置 `EGRESSCOPE_PANEL_IMAGE=rhythmlian/egresscope:latest`。

## 必需配置

| 变量 | 说明 |
| --- | --- |
| `MIHOMO_CONTROLLER_SECRET` | 与 mihomo `secret` 一致；必须使用高强度随机值 |
| `EGRESSCOPE_SESSION_SECRET` | 至少 32 字符的独立随机会话密钥 |
| `EGRESSCOPE_ADMIN_PASSWORD` | 首次启动创建管理员；数据库已有用户后不再读取 |

`EGRESSCOPE_SECURE_COOKIE` 默认 `true`，时区默认 `Asia/Shanghai`，连接明细默认保留 30 天，月度与年度汇总不会随明细清理。设备别名格式见 [`devices.example.json`](devices.example.json)。

已有 mihomo 实例时，可以只运行 `panel` 服务，并将控制器地址和只读配置挂载指向现有实例。`SSSLAB_*` 环境变量与旧数据库文件名仅作为升级兼容层保留；新部署应使用 `EGRESSCOPE_*`。

## 数据持久化与升级

持久化状态位于宿主机 `runtime/panel/`，容器内挂载为 `/data`。`/tmp` 仅是受限临时文件系统，不保存数据库。

升级前建议：

```sh
docker compose stop panel
cp -a runtime/panel "runtime/panel.backup.$(date +%Y%m%d-%H%M%S)"
docker compose pull
docker compose up -d
```

不要删除 `runtime/panel/`，除非明确希望清空用户、订阅、规则工作区和统计数据。

## ARM 与 OpenWrt

- 64 位 ARM 使用 `linux/arm64`；32 位 ARMv7 使用 `linux/arm/v7`。
- 网关模式依赖宿主机提供 TUN、host network、`NET_ADMIN`、策略路由和 nftables/iptables。容器能启动不代表透明代理链路一定完备。
- 对内存不足 1 GiB、闪存有限或 Docker 支持不完整的 OpenWrt，建议仅在路由器运行 mihomo，把 Egresscope 面板与数据库放在 NAS。

## 安全建议

- 只通过 HTTPS 访问管理面板，并阻止不受信任来源直连 `2086`。
- 不要暴露 mihomo 控制器；控制器密钥、会话密钥和管理员密码必须彼此独立。
- 订阅地址、交付链接、节点凭据和流量数据库都属于敏感信息；备份应加密并限制权限。
- 反向代理访问日志应排除 `/sub/` 交付路径，交付链接泄露后应立即轮换。
- AI 分析只发送节点名称与协议类型，不发送订阅 URL、服务器地址、端口、密码或流量明细。

安全策略和漏洞报告流程见 [`SECURITY.md`](SECURITY.md)。

## 开发

```sh
npm ci
npm run dev
.venv/bin/python -m unittest discover -s tests -v
npm run test:sites
npm run build
npm audit --audit-level=high
docker compose config
```

架构边界见 [`docs/architecture.md`](docs/architecture.md)，贡献说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，版本变化见 [`CHANGELOG.md`](CHANGELOG.md)。

## License

[GNU Affero General Public License v3.0 or later](LICENSE)。通过网络向用户提供修改版本时，也必须向这些用户提供对应源代码。
