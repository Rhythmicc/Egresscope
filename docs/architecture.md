# Egresscope architecture

Egresscope is a single-node gateway appliance. The architecture should optimize for clear ownership,
testability, and safe migrations before it optimizes for horizontal scale.

## Boundaries

### Server

The FastAPI application is the composition root. It may create services and bind routes, but domain
logic should live outside `server/main.py`.

| Boundary | Responsibility | Must not own |
| --- | --- | --- |
| `config.py` | environment parsing and immutable settings | database or network access |
| `schemas.py` | HTTP request contracts | persistence or business rules |
| `mihomo.py` | typed mihomo controller adapter | traffic attribution or Web concerns |
| `auth.py` | users, sessions and login rate limiting | subscription and gateway logic |
| `subscriptions/` | source validation, parsing, refresh and delivery profiles | rule ordering |
| `rules/` | rule workspace, validation, ordering and application | node-source ownership |
| `traffic/` | collection, reconciliation, retention and queries | HTTP response formatting |
| `gateway/` | runtime accounting and operational events | generic traffic queries |
| `api/` | route modules and dependency wiring | SQL and controller implementation details |

`server/main.py` remains a compatibility composition root while these areas move incrementally. Public
helpers imported by existing tests must be re-exported until their callers migrate.

### Web

The Web application has four layers:

1. `app/`: page registry, access rules, route state and application composition.
2. `components/`: reusable shell and domain-neutral UI.
3. `features/`: domain workspaces such as connections, traffic, rules and subscriptions.
4. `lib/`: formatting and side-effect-free utilities.

Page access is defined once in `src/app/page-map.jsx`. The sidebar, route guard and future mobile
navigation must consume that same registry so labels, order and permissions cannot drift.

The observation workspaces now live under `src/features/observability/`:

- `DashboardPage.jsx`: status overview and its shared traffic chart.
- `ConnectionsPage.jsx`: live and retained connection investigation.
- `TrafficAnalysisPage.jsx`: proxy/direct accounting and device attribution.
- `DeviceAnalysisPage.jsx`: contextual drill-down from other observation pages.

`src/app/PageRenderer.jsx` is the page outlet. `App.jsx` owns session, route and shared gateway
snapshots; it no longer owns observation-page markup.

## Migration sequence

1. Extract configuration, request schemas, the mihomo adapter, authentication, page registry, shell and
   observation workspaces.
2. Move the remaining control and management workspaces to `features/<domain>/` without changing
   their markup or API contract.
3. Split FastAPI route groups into `api/` and inject services rather than importing process globals.
4. Split traffic collection from traffic queries and add reconciliation invariants at their boundary.
5. Move subscription and rule persistence behind repositories, then add route-level integration tests.
6. Remove compatibility re-exports only after tests and external imports have migrated.

Each step must keep the production database schema, HTTP API and visible UI behavior compatible.
