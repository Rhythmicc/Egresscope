# Changelog

All notable changes to Egresscope are documented in this file.

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
