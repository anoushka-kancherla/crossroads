/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The logo image address for this app; empty means the placeholder. Not a secret. */
  readonly VITE_LOGO_URL?: string;
  /** Where the staff dashboard lives, when it cannot be worked out from this app's own address. Not a secret. */
  readonly VITE_STAFF_URL?: string;
}
