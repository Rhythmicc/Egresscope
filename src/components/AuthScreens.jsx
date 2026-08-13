import { useState } from "react";
import { Stack, WarningCircle } from "@phosphor-icons/react";

function AuthCard({ title, children }) {
  return (
    <main className="login-screen">
      <section className="login-card">
        <div className="login-brand"><span className="brand-mark"><Stack weight="fill" /></span><strong>Egresscope</strong></div>
        <div className="login-copy"><h1>{title}</h1></div>
        {children}
      </section>
    </main>
  );
}

export function LoginScreen({ onLogin, error, loading }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  return (
    <AuthCard title="登录到网关控制台">
      <form onSubmit={event => { event.preventDefault(); onLogin(username, password); }}>
        <label>用户名<input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" /></label>
        <label>密码<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" autoFocus /></label>
        {error && <div className="login-error"><WarningCircle />{error}</div>}
        <button className="login-button" disabled={loading}>{loading ? "正在登录…" : "登录"}</button>
      </form>
    </AuthCard>
  );
}

export function ServiceUnavailable({ message, retry }) {
  return (
    <AuthCard title="控制面暂时不可用">
      <div className="login-error"><WarningCircle />{message || "无法连接到网关控制面"}</div>
      <button className="login-button" onClick={retry}>重新连接</button>
    </AuthCard>
  );
}
