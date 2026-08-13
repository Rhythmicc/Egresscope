import { useEffect, useState } from "react";
import { ShieldCheck, Users, X } from "@phosphor-icons/react";
import { api } from "../../api";

const DEMO_USERS = [{ id: 1, username: "admin", role: "admin", allowedDevices: [] }];

export function UsersPage({ demoMode = false }) {
  const [users, setUsers] = useState(demoMode ? DEMO_USERS : []);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ username: "", password: "", role: "viewer", devices: "" });

  useEffect(() => {
    api.users().then(result => setUsers(result.users)).catch(error => {
      if (!demoMode) setMessage(error.message);
    });
  }, [demoMode]);

  const openCreate = () => {
    setEditingId(null);
    setForm({ username: "", password: "", role: "viewer", devices: "" });
    setShowForm(true);
  };

  const openEdit = user => {
    setEditingId(user.id);
    setForm({
      username: user.username,
      password: "",
      role: user.role,
      devices: (user.allowedDevices || []).join(", "),
    });
    setShowForm(true);
  };

  const submit = async event => {
    event.preventDefault();
    setMessage("");
    try {
      const allowedDevices = form.devices.split(",").map(item => item.trim()).filter(Boolean);
      const payload = editingId
        ? { role: form.role, allowedDevices, ...(form.password ? { password: form.password } : {}) }
        : { username: form.username, password: form.password, role: form.role, allowedDevices };
      const result = editingId ? await api.updateUser(editingId, payload) : await api.createUser(payload);
      setUsers(current => editingId
        ? current.map(item => item.id === editingId ? result.user : item)
        : [...current, result.user]);
      setShowForm(false);
      setEditingId(null);
      setMessage(editingId ? "用户权限已更新。" : "用户已创建。");
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <div className="page-content system-page">
      <div className="strategy-intro"><h2>用户与数据隔离</h2><button className="primary-button" onClick={openCreate}><Users /> 添加用户</button></div>
      {message && <div className="system-message"><ShieldCheck />{message}</div>}
      <section className="panel users-panel">
        <div className="users-head"><span>用户</span><span>角色</span><span>可见设备</span><span>权限 / 操作</span></div>
        {users.map(user => (
          <div className="user-row" key={user.id}>
            <span className="user-identity"><span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span><strong>{user.username}</strong></span>
            <span><b className={`role-badge ${user.role}`}>{user.role === "admin" ? "管理员" : "普通用户"}</b></span>
            <span className="device-scope">{user.role === "admin" ? "全部设备" : user.allowedDevices.length ? user.allowedDevices.join("、") : "无设备"}</span>
            <span className="boundary-copy"><span>{user.role === "admin" ? "全局读写" : "授权设备只读"}</span><button type="button" onClick={() => openEdit(user)}>编辑</button></span>
          </div>
        ))}
      </section>
      {showForm && (
        <div className="modal-backdrop" onMouseDown={() => setShowForm(false)}>
          <form className="user-modal" onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
            <div className="modal-heading"><h3>{editingId ? "编辑用户" : "创建用户"}</h3><button type="button" onClick={() => setShowForm(false)}><X /></button></div>
            <label>用户名<input required minLength={3} disabled={Boolean(editingId)} value={form.username} onChange={event => setForm({ ...form, username: event.target.value })} /></label>
            <label>{editingId ? "新密码（留空不修改）" : "初始密码"}<input required={!editingId} minLength={12} type="password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} /></label>
            <label>角色<select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })}><option value="viewer">普通用户</option><option value="admin">管理员</option></select></label>
            {form.role === "viewer" && <label>可见设备 IP<input value={form.devices} onChange={event => setForm({ ...form, devices: event.target.value })} placeholder="192.168.31.28, 192.168.31.46" /></label>}
            <button className="primary-button modal-submit">{editingId ? "保存权限" : "创建用户"}</button>
          </form>
        </div>
      )}
    </div>
  );
}
