/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin for cross-origin deployments. Leave empty to use same-origin /api (recommended). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
