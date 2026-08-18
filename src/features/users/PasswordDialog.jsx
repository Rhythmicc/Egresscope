import { useId, useState } from "react";
import { CheckCircle, Copy, DiceFive, Eye, EyeSlash, Key, WarningCircle, X } from "@phosphor-icons/react";
import { api } from "../../api";
import { generateRandomPassword } from "../../lib/passwords";

async function copyPassword(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  if (!copied) throw new Error("浏览器未允许复制，请手动选择密码");
}

export function GeneratedPasswordField({ label, value, onChange, required = false, autoComplete = "new-password" }) {
  const inputId = useId();
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const generate = () => {
    onChange(generateRandomPassword());
    setVisible(true);
    setCopied(false);
    setCopyError("");
  };
  const copy = async () => {
    if (!value) return;
    try {
      await copyPassword(value);
      setCopied(true);
      setCopyError("");
    } catch (error) {
      setCopied(false);
      setCopyError(error.message);
    }
  };
  return (
    <div className="password-field">
      <div className="password-field-heading"><label htmlFor={inputId}>{label}</label><small>至少 12 个字符</small></div>
      <div className="password-control">
        <input id={inputId} required={required} minLength={12} type={visible ? "text" : "password"} value={value} autoComplete={autoComplete} onChange={event => { onChange(event.target.value); setCopied(false); setCopyError(""); }} />
        <button type="button" onClick={() => setVisible(current => !current)} aria-label={visible ? "隐藏密码" : "显示密码"} title={visible ? "隐藏密码" : "显示密码"}>{visible ? <EyeSlash /> : <Eye />}</button>
        <button type="button" className="password-generate" onClick={generate} title="生成安全随机密码"><DiceFive /><span>随机生成</span></button>
        <button type="button" onClick={copy} disabled={!value} aria-label="复制密码" title="复制密码"><Copy /></button>
      </div>
      {copied && <small className="password-copied"><CheckCircle weight="fill" />密码已复制</small>}
      {copyError && <small className="password-copy-error"><WarningCircle />{copyError}</small>}
    </div>
  );
}

export function ChangePasswordDialog({ username, demoMode = false, onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);

  const submit = async event => {
    event.preventDefault();
    setMessage("");
    if (newPassword !== confirmation) {
      setMessage("两次输入的新密码不一致");
      return;
    }
    if (currentPassword === newPassword) {
      setMessage("新密码不能与当前密码相同");
      return;
    }
    setBusy(true);
    try {
      if (!demoMode) await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setSuccess(true);
      setMessage("密码已更新，其他设备上的旧会话已失效。");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={() => !busy && onClose()}>
      <form className="user-modal password-modal" onMouseDown={event => event.stopPropagation()} onSubmit={submit}>
        <div className="modal-heading"><div><span className="eyebrow">账户安全</span><h3>修改密码</h3></div><button type="button" onClick={onClose} aria-label="关闭"><X /></button></div>
        <div className="password-account"><span className="avatar">{(username || "U").slice(0, 1).toUpperCase()}</span><strong>{username}</strong></div>
        {success ? (
          <div className="password-success"><CheckCircle weight="fill" /><strong>修改成功</strong><p>{message}</p><button type="button" className="primary-button" onClick={onClose}>完成</button></div>
        ) : (
          <>
            <label>当前密码<input required type="password" autoComplete="current-password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} autoFocus /></label>
            <GeneratedPasswordField label="新密码" value={newPassword} onChange={value => { setNewPassword(value); setConfirmation(value); }} required />
            <label>确认新密码<input required minLength={12} type="password" autoComplete="new-password" value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
            {message && <div className="password-error"><WarningCircle />{message}</div>}
            <button className="primary-button modal-submit" disabled={busy}><Key weight="bold" />{busy ? "正在修改…" : "更新密码"}</button>
          </>
        )}
      </form>
    </div>
  );
}
