export function connectionExitNode(connection) {
  const explicit = String(connection?.node || "").trim();
  if (explicit) return explicit;
  const chain = Array.isArray(connection?.chain) ? connection.chain.map(String).filter(Boolean) : [];
  if (chain.includes("DIRECT")) return "DIRECT";
  return chain.at(-1) || "未识别出口";
}
