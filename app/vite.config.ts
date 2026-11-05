import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    // styles.test.ts reads the real stylesheet; by default Vitest replaces CSS with an empty file.
    css: true,
  },
})
