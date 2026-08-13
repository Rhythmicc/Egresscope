# AI feature boundary and roadmap

## Shipped foundation

The subscription assistant supports DeepSeek and OpenRouter through their OpenAI-compatible chat
completion endpoints. An administrator configures one global provider, model and API key. Every user
can analyze only a subscription they are already authorized to manage.

The model receives at most 500 node labels and protocol types. Subscription URLs, node endpoints,
ports, passwords and transport parameters never leave the appliance. The model produces a suggestion;
the user previews and edits it before applying it. Applying a filter is deterministic, rejects an
empty inventory and rolls back when a gateway hot reload fails.

## Recommended next features

### 1. Explain deterministic anomaly detections

The collector should detect anomalies locally first, using rolling median/MAD baselines, new-domain
cardinality, unexpected country/ASN changes, connection failure rate and proxy-cost spikes. AI can
then explain a compact aggregate event and propose investigation steps. It must not decide that a
device is malicious or receive raw browsing history by default.

### 2. Rule suggestions from repeated manual actions

When an administrator repeatedly terminates or reroutes the same host, offer a draft DOMAIN-SUFFIX or
RULE-SET rule. AI may explain overlap and ordering conflicts, but the existing deterministic rule
validator remains the authority and applying the draft remains an explicit administrator action.

### 3. Node-health incident summaries

Correlate latency, timeout, handshake and strategy-switch events locally. AI can group likely causes
such as provider outage, regional degradation or a single unhealthy node and generate a concise
incident summary. It must not automatically delete nodes or rewrite strategy topology.

### 4. Quota and cost forecasting

Forecast the current subscription reset cycle from persisted proxy bytes, identify the devices and
services driving the change, and estimate exhaustion dates. The numeric forecast remains local and
reproducible; AI only turns it into a readable explanation.

### 5. Configuration migration assistant

Parse Surge, Clash/Mihomo and common provider formats locally, then use AI only for ambiguous labels,
group intent and cleanup suggestions. A structural diff must be shown before saving, and secrets must
be redacted from prompts and diffs.

## Non-goals

- Sending raw URLs, credentials, full connection logs or device browsing history to a model.
- Letting model output bypass schema, regex, rule-order or mihomo validation.
- Automatically applying traffic blocks, deleting nodes or changing policies without confirmation.
- Treating an LLM narrative as an anomaly detector or a security verdict.
