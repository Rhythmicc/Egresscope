# Changelog

All notable changes to Egresscope are documented in this file.

## [0.4.1] - 2026-08-21

### Fixed

- Keep merged Surge and Clash/Mihomo delivery URLs available when automatic combo exit rotation is paused. Delivery URLs are revoked only by rotating their token or deleting the combo.

## [0.4.0] - 2026-08-21

### Added

- Owner-scoped combined profiles that merge multiple subscriptions into one Clash/Surge delivery and one optional gateway source.
- Deterministic country- and city-aware exit rotation with health, latency, provider-usage, and diversity preferences.
- Offline/online GeoIP resolution, manual region correction, and gateway exit probing.
- Web-managed mihomo kernel staging, verification, switching, and rollback.
- One-time subscription-link lifecycle support with persisted usage snapshots and provider-health events.

### Changed

- Dashboard live data refreshes once per second without overlapping requests; chart animation is disabled during live updates.
- Dashboard historical aggregation is cached while live connections and rates remain current, reducing control-plane latency.
- Rotation now closes only connections affected by a changed regional selector so new requests cannot coexist indefinitely on stale exits.
- Strategy, node, rule, and traffic displays preserve provider emoji and use consistent inferred region flags when needed.
- Wide desktop, tablet, and mobile layouts expose denser operational information without page-level overflow.

### Security

- Combination ownership and delivery tokens are enforced server-side; ordinary users can only combine their own subscriptions.
- GeoIP and kernel downloads are size-limited, validated, and isolated from sensitive controller configuration.
- Public release packaging excludes local design QA, audit screenshots, runtime databases, secrets, and deployment handoff notes.

## [0.3.0] - 2026-08-18

### Added

- Durable connection history, device-to-destination attribution, and monthly/yearly traffic accounting.
- Traffic anomaly guard with a configurable time window, threshold, and response policy.
- Ordered rule sets, custom override rules, rule validation, and optional GitHub synchronization.
- Subscription filtering, renaming rules, delivery links, and optional DeepSeek/OpenRouter suggestions.
- Multi-user roles, device visibility, self-service password changes, and random password generation.
- Strategy delay tests, selector changes, affected-connection reconnection, and editable secondary selectors.
- Responsive desktop, tablet, and mobile management interfaces.

### Changed

- Traffic charts and device analysis now report accumulated bytes instead of long-period average speed.
- Connection tables show the effective exit node while retaining rule and policy details in drill-down views.
- Infrastructure sources are excluded from device and live-connection lists without removing their bytes from gateway totals.
- The production Compose deployment is pinned to the `0.3.0` panel image and uses durable `/data` storage.

### Security

- Hardened subscription fetching against private-network targets, oversized responses, and credential-bearing error messages.
- Added login throttling, revocable sessions, production secret validation, secure-cookie defaults, and delivery-link rotation.
- Reduced container privileges and documented HTTPS, controller isolation, backup, and sensitive-log requirements.
