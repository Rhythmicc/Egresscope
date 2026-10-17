const userInfo = value => encodeURIComponent(value).replace(/[!'()*]/g, character => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
const shellQuote = value => `'${value.replace(/'/g, "'\\''")}'`;

export function proxyEnvironment(config, credentials = [], accountId = config.accounts[0]?.id) {
  const listeners = config.listeners.filter(listener => listener.host && listener.port > 0);
  const http = listeners.find(listener => listener.id === "mixed-port") || listeners.find(listener => listener.id === "port");
  const socks = listeners.find(listener => listener.id === "mixed-port") || listeners.find(listener => listener.id === "socks-port");
  const primary = http || socks;
  if (!primary) throw new Error("没有可用的代理接入地址，请刷新配置。");
  const expected = config.accounts.find(account => account.id === accountId);
  const account = credentials.find(item => item.id === accountId && item.username === expected?.username);
  if (config.accounts.length && (!expected || !account || typeof account.password !== "string")) {
    throw new Error("认证账户已变化，请刷新代理配置。");
  }
  const auth = expected ? `${userInfo(account.username)}:${userInfo(account.password)}@` : "";
  const host = listener => listener.host.includes(":") ? `[${listener.host.replace(/^\[|\]$/g, "")}]` : listener.host;
  const scheme = http ? "http" : "socks5h";
  const lines = [
    `export BASIC_PROXY=${shellQuote(`${scheme}://${auth}${host(primary)}`)}`,
    `export HTTP_PROXY="$BASIC_PROXY:${primary.port}"`,
    'export HTTPS_PROXY="$HTTP_PROXY"',
    socks ? `export ALL_PROXY=${shellQuote(`socks5h://${auth}${host(socks)}:${socks.port}`)}` : 'export ALL_PROXY="$HTTP_PROXY"',
    'export http_proxy="$HTTP_PROXY"',
    'export https_proxy="$HTTPS_PROXY"',
    'export all_proxy="$ALL_PROXY"',
    'export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"',
    'export no_proxy="$NO_PROXY"',
  ];
  return `${lines.join("\n")}\n`;
}
