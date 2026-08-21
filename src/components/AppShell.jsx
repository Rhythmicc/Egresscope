import { Desktop, Moon, Rows, SignOut, Stack, Sun } from "@phosphor-icons/react";
import { visiblePages } from "../app/page-map";

function StatusPill({ online }) {
  return (
    <div className={`status-pill ${online ? "is-online" : "is-offline"}`}>
      <span className="status-dot" />
      <span className="status-copy">{online ? "网关运行正常" : "网关连接中断"}</span>
    </div>
  );
}

const THEME_OPTIONS = [
  { value: "light", icon: Sun, label: "浅色" },
  { value: "system", icon: Desktop, label: "跟随系统" },
  { value: "dark", icon: Moon, label: "深色" },
];

function ThemeSwitcher({ theme, setTheme }) {
  return (
    <div className="theme-switcher" role="radiogroup" aria-label="主题模式">
      {THEME_OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          aria-label={label}
          title={label}
          className={theme === value ? "active" : ""}
          onClick={() => setTheme(value)}
        >
          <Icon weight={theme === value ? "fill" : "regular"} />
        </button>
      ))}
    </div>
  );
}

export function Sidebar({ page, setPage, collapsed, setCollapsed, online, theme, setTheme, onAccount, onLogout, user }) {
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
      <div className="sidebar-global">
        <StatusPill online={online} />
        <ThemeSwitcher theme={theme} setTheme={setTheme} />
        <div className="sidebar-account">
          <button type="button" className="profile-identity" onClick={onAccount} aria-label={`修改 ${user?.username || "demo"} 的密码`} title="修改密码">
            <span className="avatar">{(user?.username || "demo").slice(0, 1).toUpperCase()}</span>
            <span>{user?.username || "demo"}</span>
          </button>
          <div className="sidebar-actions">
            <button className="icon-button" onClick={onLogout} aria-label="退出登录" title="退出登录"><SignOut /></button>
          </div>
        </div>
      </div>
      <button className="collapse-button" aria-label={collapsed ? "展开侧栏" : "收起侧栏"} title={collapsed ? "展开侧栏" : "收起侧栏"} onClick={() => setCollapsed(!collapsed)}>
        <Rows /> <span>收起侧栏</span>
      </button>
    </aside>
  );
}

export function Topbar({ title, online, theme, setTheme, onAccount, onLogout, user }) {
  return (
    <header className="topbar">
      <div className="page-title"><h1>{title}</h1></div>
      <div className="topbar-actions">
        <StatusPill online={online} />
        <span className="last-refresh">刚刚刷新</span>
        <ThemeSwitcher theme={theme} setTheme={setTheme} />
        <button type="button" className="profile-identity" onClick={onAccount} aria-label={`修改 ${user?.username || "demo"} 的密码`} title="修改密码">
          <span className="avatar">{(user?.username || "demo").slice(0, 1).toUpperCase()}</span>
          <span>{user?.username || "demo"}</span>
        </button>
        <button className="icon-button" onClick={onLogout} aria-label="退出登录" title="退出登录"><SignOut /></button>
      </div>
    </header>
  );
}
