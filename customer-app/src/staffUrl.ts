type Where = Pick<Location, "protocol" | "hostname" | "port">;

/** Where the staff dashboard lives, worked out from the address this app was opened on so no rebuild is
 *  needed per environment: app.<host> -> internal.<host>, and the local ports 8080 -> 8081, 5173 -> 5174.
 *  VITE_STAFF_URL (the override) wins; null means the layout is not recognised. */
export function staffUrl(loc: Where, override?: string): string | null {
  if (override) return override;
  const { protocol, hostname, port } = loc;
  if (hostname.startsWith("app.")) return `${protocol}//internal.${hostname.slice(4)}${port ? `:${port}` : ""}/`;
  if (port === "8080") return `${protocol}//${hostname}:8081/`;
  if (port === "5173") return `${protocol}//${hostname}:5174/`;
  return null;
}
