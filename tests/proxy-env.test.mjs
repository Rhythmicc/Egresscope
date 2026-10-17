import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";
import { proxyEnvironment } from "../src/features/gateway/proxy-env.js";

const listener = (id = "mixed-port", port = 9999, host = "192.168.1.12") => ({ id, port, host });
const config = { listeners: [listener()], accounts: [{ id: 0, username: "example" }] };
const credentials = [{ id: 0, username: "example", password: "test-value" }];
const variables = ["BASIC_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy", "NO_PROXY", "no_proxy"];
const run = (snippet, env = {}) => execFileSync("/bin/sh", ["-c", snippet + '\nprintf "%s\\n" ' + variables.map(name => `"$${name}"`).join(" ")], { encoding: "utf8", env: { ...process.env, NO_PROXY: "", ...env } }).trim().split("\n");

test("mixed listener exports executable upper/lowercase HTTP, HTTPS, SOCKS and bypass variables", () => {
  const snippet = proxyEnvironment(config, credentials);
  assert.match(snippet, /^export BASIC_PROXY=/);
  assert.match(snippet, /export HTTP_PROXY="\$BASIC_PROXY:9999"/);
  assert.deepEqual(run(snippet), ["http://example:test-value@192.168.1.12", "http://example:test-value@192.168.1.12:9999", "http://example:test-value@192.168.1.12:9999", "socks5h://example:test-value@192.168.1.12:9999", "http://example:test-value@192.168.1.12:9999", "http://example:test-value@192.168.1.12:9999", "socks5h://example:test-value@192.168.1.12:9999", "localhost,127.0.0.1,::1", "localhost,127.0.0.1,::1"]);
});

test("separate HTTP/SOCKS ports and IPv6 addresses are preserved", () => {
  const values = run(proxyEnvironment({ ...config, listeners: [listener("port", 8080, "2001:db8::12"), listener("socks-port", 1080, "2001:db8::12")] }, credentials));
  assert.equal(values[1], "http://example:test-value@[2001:db8::12]:8080");
  assert.equal(values[3], "socks5h://example:test-value@[2001:db8::12]:1080");
});

test("credentials with shell metacharacters and URL delimiters remain literal userinfo", () => {
  const username = "a'b;$(exit 31)@name";
  const password = "p\"`$();:@/!#% value";
  const values = run(proxyEnvironment({ ...config, accounts: [{ id: 0, username }] }, [{ id: 0, username, password }]));
  const url = new URL(values[1]);
  assert.equal(decodeURIComponent(url.username), username);
  assert.equal(decodeURIComponent(url.password), password);
});

test("unauthenticated listeners do not require or invent credentials", () => {
  const values = run(proxyEnvironment({ listeners: [listener()], accounts: [] }));
  assert.equal(values[1], "http://192.168.1.12:9999");
  assert.equal(values[3], "socks5h://192.168.1.12:9999");
});

test("single-protocol listeners use only a protocol that is actually available", () => {
  assert.equal(run(proxyEnvironment({ listeners: [listener("port", 8080)], accounts: [] }))[3], "http://192.168.1.12:8080");
  assert.equal(run(proxyEnvironment({ listeners: [listener("socks-port", 1080)], accounts: [] }))[1], "socks5h://192.168.1.12:1080");
});

test("account selection matches the live metadata and rejects stale credentials", () => {
  const multi = { ...config, accounts: [...config.accounts, { id: 1, username: "second" }] };
  const accounts = [...credentials, { id: 1, username: "second", password: "second-value" }];
  assert.equal(new URL(run(proxyEnvironment(multi, accounts, 1))[1]).username, "second");
  assert.throws(() => proxyEnvironment(config, [{ id: 0, username: "changed", password: "test" }]), /账户已变化/);
  assert.throws(() => proxyEnvironment(config, []), /账户已变化/);
});

test("missing addresses fail and an existing NO_PROXY remains intact", () => {
  assert.throws(() => proxyEnvironment({ ...config, listeners: [listener("mixed-port", 9999, null)] }, credentials), /没有可用/);
  assert.equal(run(proxyEnvironment(config, credentials), { NO_PROXY: "localhost,.example.test" })[7], "localhost,.example.test");
});
