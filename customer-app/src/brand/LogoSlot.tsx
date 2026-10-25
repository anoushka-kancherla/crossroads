import { type CSSProperties, useState } from "react";

/** A fixed-size box for the logo, shown in the brand colour. With no logo set (or one that fails to load) a placeholder of the same
 *  size is shown, so the layout never shifts. The address comes from the build setting VITE_LOGO_URL. */
export function LogoSlot({ size = "header" }: { size?: "header" | "card" }) {
  const url = import.meta.env.VITE_LOGO_URL;
  const [failed, setFailed] = useState(false);
  const shown = Boolean(url && !failed);
  return (
    <span className={`logo-slot logo-${size}${shown ? " has-logo" : ""}`}>
      {shown ? (
        <>
          {/* The logo is drawn as a mask over the brand colour, so a one-colour (for example black) file
              takes the brand green; this hidden image only tells us if the file fails to load. */}
          <span className="logo-mask" style={{ "--logo-url": `url("${url}")` } as CSSProperties} />
          <img className="logo-probe" src={url} alt="" onError={() => setFailed(true)} />
        </>
      ) : (
        <span className="logo-placeholder">Your logo</span>
      )}
    </span>
  );
}
