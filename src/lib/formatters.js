export const bytes = (value = 0) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Number(value) || 0;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount >= 100 || unit === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unit]}`;
};

export const rate = (value = 0) => `${bytes(value)}/s`;

export const bucketDuration = (seconds = 0) => (
  seconds >= 86400 ? `${seconds / 86400} 天`
    : seconds >= 3600 ? `${seconds / 3600} 小时`
      : seconds >= 60 ? `${seconds / 60} 分钟`
        : `${seconds} 秒`
);

export const connectionDuration = (seconds = 0) => {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  const secs = Math.floor(value % 60);
  return hours ? `${hours}时 ${minutes}分` : minutes ? `${minutes}分 ${secs}秒` : `${secs}秒`;
};

export const connectionTime = timestamp => timestamp
  ? new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(timestamp * 1000))
  : "—";
