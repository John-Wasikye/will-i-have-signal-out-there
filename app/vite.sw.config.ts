// Builds the report sender (src/sw.ts) into dist/sw.js after the site build. It is one classic
// script with nothing shared with the page's files, because module service workers are not
// supported in every browser. It must sit at the site root so it can serve every page.
import { defineConfig } from 'vite'

export default defineConfig({
  publicDir: false,
  build: {
    emptyOutDir: false,
    lib: {
      entry: 'src/sw.ts',
      formats: ['iife'],
      name: 'signalReportSender',
      fileName: () => 'sw.js',
    },
  },
})
