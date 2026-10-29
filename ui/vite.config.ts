import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0', port: 5173, strictPort: true,
    // Opt-in fallback for WSL/shared hosts with exhausted inotify watches.
    watch: process.env.WEAVEM_UI_POLL === '1' ? { usePolling: true, interval: 250 } : undefined,
  },
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
});
