import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * The 3D client talks to one origin: the gateway on :8000.
 * `/api/*` and `/ws` are proxied, so the browser never needs to know service ports — and the same
 * build works behind the preview host without any host allowlist surprises.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: false,
    // The preview host is not localhost; accept it (auth still gates the API).
    allowedHosts: true as unknown as string[],
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: false },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 1600 },
});
