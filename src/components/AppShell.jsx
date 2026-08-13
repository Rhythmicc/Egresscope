import { Desktop, Moon, Rows, SignOut, Stack, Sun } from "@phosphor-icons/react";
import { visiblePages } from "../app/page-map";

function StatusPill({ online }) {
  return (
    <div className={`status-pill ${online ? "is-online" : "is-offline"}`}>
      <span className="status-dot" />
      {online ? "网关运行正常" : "网关连接中断"}
    </div>
  );
}

export function Sidebar({ page, setPage, collapsed, setCollapsed, user }) {
  return (
    <aside className={`sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <button className="brand" onClick={() => setPage("dashboard")} aria-label="返回状态概览">
        <span className="brand-mark"><Stack weight="fill" /></span>
        <span>Egresscope</span>
      </button>
      <nav className="nav-list" aria-label="主导航">
        {visiblePages(user).map(item => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => setPage(item.id)}
              title={item.label}
            >
              <Icon weight={page === item.id ? "fill" : "regular"} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <button className="collapse-button" aria-label={collapsed ? "展开侧栏" : "收起侧栏"} title={collapsed ? "展开侧栏" : "收起侧栏"} onClick={() => setCollapsed(!collapsed)}>
        <Rows /> <span>收起侧栏</span>
      </button>
    </aside>
  );
}

export function Topbar({ title, online, theme, cycleTheme, onLogout, user }) {
  return (
    <header className="topbar">
      <div className="page-title"><h1>{title}</h1></div>
      <div className="topbar-actions">
        <StatusPill online={online} />
        <span className="last-refresh">刚刚刷新</span>
        <button className="icon-button theme-button" onClick={cycleTheme} title={`当前：${theme}`}>
          {theme === "dark" ? <Moon weight="fill" /> : theme === "light" ? <Sun weight="fill" /> : <Desktop />}
        </button>
        <div className="profile-identity" aria-label={`当前用户：${user?.username || "demo"}`}>
          <span className="avatar">{(user?.username || "demo").slice(0, 1).toUpperCase()}</span>
          <span>{user?.username || "demo"}</span>
        </div>
        <button className="icon-button" onClick={onLogout} title="退出登录"><SignOut /></button>
      </div>
    </header>
  );
}
