import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// GitHub Pages serves the site under /nwoma/.
export default defineConfig({
  base: '/nwoma/',
  plugins: [react()],
  test: { environment: 'node' },
})
