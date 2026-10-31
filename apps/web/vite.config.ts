import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy: the FastAPI server (W2) runs on :8787 and owns /api and /files.
declare const process: {env: Record<string,string|undefined>};
const SERVER = process.env.TYPESET_SERVER ?? 'http://localhost:8787';

export default defineConfig({
  // Relative base: the same build serves at / (FastAPI :8787) and at /typeset/ inside ComfyUI.
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: SERVER, changeOrigin: true },
      '/files': { target: SERVER, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
  },
});
