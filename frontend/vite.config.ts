import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Splits stable third-party code from app code so a route-chunk
        // update (the normal case — see AppRouter.tsx's per-role lazy
        // imports) doesn't force browsers to re-download vendor libraries
        // they already cached from a previous visit. Grouped by how often
        // each group actually changes, not by package name (P7.7 — mobile
        // browser support: smaller, better-cached initial loads matter
        // most on slower connections).
        //
        // Matched by node_modules path (function form), not the object-form
        // package-name array: a bare package name only pins that package's
        // resolved entry point, not its internal submodules. React ships its
        // real implementation behind an internal cjs/react.production.js
        // require that isn't the package entry point, so name-only matching
        // let it drift into vendor-ui and form a circular chunk import with
        // vendor-react at runtime. Path matching keeps every submodule of a
        // package in the same chunk regardless of which group imports it.
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom)[\\/]/.test(id)) {
            return 'vendor-react';
          }
          if (/[\\/]node_modules[\\/](@tanstack[\\/]react-query|axios|zod|react-hook-form)[\\/]/.test(id)) {
            return 'vendor-data';
          }
          if (
            /[\\/]node_modules[\\/](@radix-ui|lucide-react|class-variance-authority|clsx|tailwind-merge)[\\/]/.test(
              id,
            )
          ) {
            return 'vendor-ui';
          }
        },
      },
    },
  },
});
