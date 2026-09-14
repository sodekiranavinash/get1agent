import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Local dev routes API calls through the Vite dev server instead of hitting
// Floci cross-origin: Floci's API Gateway only emits CORS headers on the
// preflight, not on the proxied response, so the browser blocks the real call.
// Set VITE_API_PROXY_TARGET to the Floci API URL (and VITE_API_URL to "/") to
// keep requests same-origin. Unset (production) leaves the proxy disabled.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: proxyTarget
      ? {
          proxy: {
            '/v1': { target: proxyTarget, changeOrigin: true },
          },
        }
      : undefined,
  }
})
