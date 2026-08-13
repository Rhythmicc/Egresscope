# Web page map

## Primary map

The current eight-item order is sound when it is understood as three task groups. The groups should be
communicated by spacing and route metadata, not by adding more permanent sidebar copy.

| Task group | Page | Viewer | Primary job |
| --- | --- | --- | --- |
| Observe | 状态概览 | yes | decide whether the gateway needs attention |
| Observe | 连接统计 | yes | investigate current and retained sessions |
| Observe | 流量分析 | yes | account for traffic cost by service, target and device |
| Control | 分流策略 | admin | choose an exit behavior or node |
| Control | 规则管理 | admin | decide which requests enter each policy |
| Manage | 订阅管理 | yes | manage personal node delivery; admins also select the gateway source |
| Manage | 网关设置 | admin | inspect runtime/events and name source devices |
| Manage | 用户管理 | admin | grant roles and device scope |

This ordering follows the normal operating loop: observe a symptom, change routing behavior, then
maintain the system that supplies that behavior. `订阅管理` remains visible to viewers because it is
also a personal-delivery workspace, not only gateway administration.

## Secondary destinations

These are contextual destinations, not additional primary-navigation items:

- `设备分析`: a child of observability, opened from 状态概览、连接统计 or 流量分析. It should have a
  durable device route so refresh and sharing preserve context.
- `连接详情`: a drawer or sheet over 连接统计. It should not replace the current filters and result set.
- `创建规则`: a contextual transition from a connection into 规则管理, preserving host, source device
  and current policy as a draft.
- `网关运行统计 / 事件记录 / 设备管理`: tabs inside 网关设置 because they describe one appliance.
- `订阅编辑 / 交付链接`: modal or card-level actions inside 订阅管理.

## Route rules

- Unknown or unauthorized routes resolve to 状态概览 without briefly rendering protected content.
- The active primary page is represented in the URL and survives refresh.
- The old `?page=system` link remains compatible but normalizes to `?page=users`.
- Viewer and administrator navigation are generated from the same page registry used by route guards.
- Phone bottom navigation keeps the same order. It may scroll horizontally, but must not hide viewer
  pages or move administrator-only pages into an unrelated generic menu.

## Highest-impact remaining changes

1. Give 设备分析 a durable child route with device identity in the URL.
2. Preserve list filters and scroll position when returning from a device or connection detail.
3. Add subtle visual separation after 流量分析 and 规则管理 on desktop/tablet navigation.
4. Move the remaining control and management pages out of `App.jsx`; observation pages and the page
   renderer have already migrated.
5. Verify the tablet breakpoint: the captured 1024 px state still used the full desktop sidebar and
   caused wide workspaces to crop instead of switching to the specified compact rail.
