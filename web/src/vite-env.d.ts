/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Server origin for deployed builds; empty in development (Vite proxies /api). */
  readonly VITE_API_BASE_URL?: string
}
