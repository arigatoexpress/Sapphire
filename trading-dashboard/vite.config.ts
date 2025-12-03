import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false, // Disable sourcemaps in production for smaller bundle
    minify: 'terser', // Use terser for better minification
    terserOptions: {
      compress: {
        drop_console: true, // Remove console.log in production
        drop_debugger: true,
      },
    },
    chunkSizeWarningLimit: 1000, // Warn for chunks over 1MB
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          firebase: ['firebase/app', 'firebase/auth', 'firebase/firestore'],
          mui: ['@mui/material', '@mui/icons-material', '@mui/x-charts', '@mui/x-data-grid'],
          charts: ['recharts'],
        },
        // Optimize chunk names
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]',
      },
    },
    // Enable tree-shaking and optimize assets
    cssCodeSplit: true,
    reportCompressedSize: true,
  },
  server: {
    port: 3000,
      host: true,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8080',
          changeOrigin: true,
        },
        '/ws': {
          target: env.VITE_API_URL || 'http://localhost:8080',
          changeOrigin: true,
          ws: true,
        },
      },
  },
  // Optimize dependencies
  optimizeDeps: {
    include: ['react', 'react-dom', '@mui/material', 'firebase/app'],
  },
  }
})
