# Security policy

Please report vulnerabilities privately through GitHub Security Advisories. Do not
open a public issue with credentials, subscription URLs, controller secrets, IP
addresses, or traffic records.

Supported releases are the latest tagged release and the current `main` branch.

Production deployments must terminate HTTPS before port 2086, keep the mihomo
controller bound to loopback, use independent random secrets, and prevent direct
untrusted access to port 2086. Subscription delivery URLs are bearer credentials;
rotate them after accidental disclosure and exclude `/sub/` paths from access logs.
