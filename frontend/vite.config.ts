import react from '@vitejs/plugin-react';
import tsconfigPaths from 'vite-tsconfig-paths';

import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  // Build-unique id used to cache-bust runtime-fetched assets (i18n locale files).
  define: {
    __BUILD_ID__: JSON.stringify(Date.now().toString()),
  },
  plugins: [react(), tsconfigPaths()],
});
