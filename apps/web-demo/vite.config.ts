import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@pair/types': path.resolve(__dirname, '../../packages/types/src/index.ts'),
      '@pair/question-definitions': path.resolve(__dirname, '../../packages/question-definitions/src/index.ts'),
      '@pair/wizard-engine': path.resolve(__dirname, '../../packages/wizard-engine/src/index.ts'),
    },
  },
});
