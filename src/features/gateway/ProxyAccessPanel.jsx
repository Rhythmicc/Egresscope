import { useEffect, useRef, useState } from "react";
import { ArrowClockwise, Copy, Eye, EyeSlash } from "@phosphor-icons/react";
import { api } from "../../api";
import "./proxy-access.css";

async function copyText(value) {
  if (!navigator.clipboard?.writeText) throw new Error("当前浏览器不支持复制，请手动选择复制。");
  try { await navigator.clipboard.writeText(value); }
  catch { throw new Error("复制失败，请允许浏览器访问剪贴板或手动选择复制。"); }
}

function ProxyAccount({ account, onMessage }) {
  const [password, setPassword] = useState(null);
  const [busy, setBusy] = useState(false);
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  const readPassword = async (copy = false) => {
    setBusy(true);
    onMessage("");
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await api.gatewayProxyCredentials({ signal: controller.signal });
      if (controller.signal.aborted) return;
      const current = result.accounts.find(item => item.id === account.id && item.username === account.username);
      if (!current || typeof current.password !== "string") throw new Error("认证账户已变化，请刷新代理配置。");
      if (copy) { await copyText(current.password); onMessage("密码已复制。"); }
      else setPassword(current.password);
    } catch (error) { if (!controller.signal.aborted) onMessage(error.message); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const copyUsername = async () => {
    try { await copyText(account.username); onMessage("用户名已复制。"); }
    catch (error) { onMessage(error.message); }
  };
  return <article className="proxy-account">
    <div className="proxy-field"><span>用户名</span><code>{account.username || "（空用户名）"}</code><button className="filter-button" onClick={copyUsername} aria-label={`复制用户名 ${account.username}`}><Copy aria-hidden="true" />复制</button></div>
    <div className="proxy-field proxy-password"><span>密码</span>{password === null ? <code aria-label="密码未显示">••••••••</code> : <input aria-label={`密码（${account.username}）`} readOnly value={password} autoComplete="off" spellCheck={false} />}
      <div className="proxy-field-actions"><button className="filter-button" disabled={busy} aria-pressed={password !== null} onClick={() => password === null ? readPassword() : setPassword(null)}>{password === null ? <Eye aria-hidden="true" /> : <EyeSlash aria-hidden="true" />}{password === null ? "显示密码" : "隐藏密码"}</button><button className="filter-button" disabled={busy} onClick={() => readPassword(true)}><Copy aria-hidden="true" />复制密码</button></div>
    </div>
  </article>;
}

export function ProxyAccessPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(""); setMessage(""); setLoading(true);
    api.gatewayProxy({ signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setData(result);
    }).catch(failure => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  const copyAddress = async address => {
    try { await copyText(address); setMessage("代理地址已复制。"); }
    catch (failure) { setMessage(failure.message); }
  };
  return <section className="panel proxy-access" aria-labelledby="proxy-access-title">
    <div className="proxy-access-head"><div><h2 id="proxy-access-title">显式代理配置</h2><p>HTTP / SOCKS5 客户端接入</p></div><button className="filter-button" disabled={loading} onClick={() => setRevision(value => value + 1)}><ArrowClockwise aria-hidden="true" />刷新配置</button></div>
    {loading && <p role="status">正在读取当前代理配置…</p>}
    {error && <p className="proxy-feedback proxy-error" role="alert">{error}</p>}
    {message && <p className="proxy-feedback" role="status">{message}</p>}
    {data && <>
      <div className="proxy-listeners">{data.listeners.map(listener => <article className="proxy-listener" key={listener.id}><span>{listener.protocol}</span><strong><code>{listener.address || `端口 ${listener.port}`}</code></strong>{listener.address ? <button className="filter-button" onClick={() => copyAddress(listener.address)} aria-label={`复制 ${listener.protocol} 代理地址`}><Copy aria-hidden="true" />复制地址</button> : <small>未检测到接入地址，请使用网关所在主机的地址。</small>}</article>)}</div>
      {!data.listeners.length && <p className="proxy-feedback">当前未启用 HTTP / SOCKS5 代理端口。</p>}
      <div className="proxy-network"><span className="proxy-access-badge">{data.allowLan ? "允许局域网接入" : "仅本机接入"}</span><span>监听地址 <code>{data.bindAddress}</code></span></div>
      <h3>认证账户</h3>
      {data.accounts.length ? data.accounts.map(account => <ProxyAccount key={`${account.id}:${account.username}`} account={account} onMessage={setMessage} />) : <p className="proxy-feedback">未启用用户名密码认证。</p>}
      {data.skipAuthPrefixes.length > 0 && <div className="proxy-prefixes"><span>免认证来源</span><div>{data.skipAuthPrefixes.map(prefix => <code key={prefix}>{prefix}</code>)}</div></div>}
      {data.lanAllowedIPs.length > 0 && <div className="proxy-prefixes"><span>允许接入网段</span><div>{data.lanAllowedIPs.map(prefix => <code key={prefix}>{prefix}</code>)}</div></div>}
      {data.lanDisallowedIPs.length > 0 && <div className="proxy-prefixes"><span>禁止接入网段</span><div>{data.lanDisallowedIPs.map(prefix => <code key={prefix}>{prefix}</code>)}</div></div>}
    </>}
  </section>;
}
