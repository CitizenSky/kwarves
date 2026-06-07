import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  base: '/kwarves/dashboard/',
  publicDir: 'data',
  build: {
    outDir: 'dist',
    emptyOutDir: true
  },
  test: {
    globals: true,
    environment: 'node'
  }
});
