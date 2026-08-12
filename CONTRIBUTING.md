# Contributing

Use Python 3.12+ and Node.js 22+. Keep the control plane independent from node and
rule sources, preserve per-user device scoping, and add a migration for every schema
change. Never commit real subscription URLs, node credentials, database files, or
NAS configuration.

When changing Python dependencies, regenerate `requirements.lock` with Python 3.12
and `pip-compile --generate-hashes requirements.txt`.

Before submitting a change, run:

```sh
python3 -m unittest discover -s tests -v
npm run test:sites
npm run build
npm audit --audit-level=high
docker compose config
```

Security-sensitive changes should include negative tests for authorization, URL
validation, size limits, and rollback behavior.
