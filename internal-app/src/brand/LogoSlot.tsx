import { useState } from "react";

/** A fixed-size box for the logo. With no logo set (or one that fails to load) a placeholder of the same
 *  size is shown, so the layout never shifts. The address comes from the build setting VITE_LOGO_URL. */
export function LogoSlot({ size = "header" }: { size?: "header" | "card" }) {
  const url = import.meta.env.VITE_LOGO_URL;
  const [failed, setFailed] = useState(false);
  return (
    <span className={`logo-slot logo-${size}`}>
      {url && !failed ? (
        <img src={url} alt="" onError={() => setFailed(true)} />
      ) : (
        <span className="logo-placeholder">Your logo</span>
      )}
    </span>
  );
}
