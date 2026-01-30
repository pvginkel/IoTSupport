import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

function backendProxyStatusPlugin(target: string): Plugin {
  const probeUrl = new URL('/api/health', target).toString()

  const checkBackend = async () => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000)

    try {
      const response = await fetch(probeUrl, { signal: controller.signal })
      if (!response.ok) {
        console.warn(
          `\n⚠️  WARNING: Backend at ${target} responded with ${response.status}.\n` +
          `   Ensure the backend is running or update BACKEND_URL.\n` +
          `   The dev server will start, but API calls will fail until the backend is available.\n`
        )
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown error'
      console.warn(
        `\n⚠️  WARNING: Unable to reach backend at ${target}.\n` +
        `   Reason: ${reason}\n` +
        `   Start the backend or set BACKEND_URL to a reachable URL.\n` +
        `   The dev server will start, but API calls will fail until the backend is available.\n`
      )
    } finally {
      clearTimeout(timeoutId)
    }
  }

  const safeCheck = () => {
    checkBackend().catch(() => {
      // Connectivity issues are already reported above; no additional handling required.
    })
  }

  return {
    name: 'backend-proxy-status',
    configureServer() {
      safeCheck()
    },
    configurePreviewServer() {
      safeCheck()
    }
  }
}

const backendProxyTarget = process.env.BACKEND_URL || 'http://localhost:3201'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react(), backendProxyStatusPlugin(backendProxyTarget)],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@/components': path.resolve(__dirname, './src/components'),
      '@/routes': path.resolve(__dirname, './src/routes'),
      '@/lib': path.resolve(__dirname, './src/lib'),
      '@/hooks': path.resolve(__dirname, './src/hooks'),
      '@/types': path.resolve(__dirname, './src/types'),
      // In test mode, replace esptool-js with mock implementation
      // This enables Playwright testing without actual ESP32 hardware
      ...(process.env.VITE_TEST_MODE === 'true' ? {
        'esptool-js': path.resolve(__dirname, './tests/support/mocks/esptool-mock.ts'),
      } : {}),
    },
  },
  server: {
    host: true,
    port: 3200,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: backendProxyTarget,
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.headers.host) {
              proxyReq.setHeader('X-Forwarded-Host', req.headers.host);
              proxyReq.setHeader('X-Forwarded-Proto', 'http');
            }
          });
        },
      }
    },
    watch: process.env.VITE_TEST_MODE === 'true'
      ? {
          ignored: ['**']
        }
      : undefined
  },
  preview: {
    proxy: {
      '/api': {
        target: backendProxyTarget,
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.headers.host) {
              proxyReq.setHeader('X-Forwarded-Host', req.headers.host);
              proxyReq.setHeader('X-Forwarded-Proto', 'http');
            }
          });
        },
      }
    }
  },
  define: {
    // Force VITE_TEST_MODE to 'false' in production builds.
    // This enables Vite to tree-shake all `if (isTestMode()) { ... }` blocks,
    // eliminating test instrumentation code from production bundles.
    // In development, use the environment variable if set.
    'import.meta.env.VITE_TEST_MODE': process.env.NODE_ENV === 'production'
      ? JSON.stringify('false')
      : JSON.stringify(process.env.VITE_TEST_MODE || 'false'),
  },
  build: {
    chunkSizeWarningLimit: 2000
  },
  optimizeDeps: {
    // esptool-js dynamically imports chip-specific modules at runtime.
    // Pre-bundle them to avoid 504 Outdated Optimize Dep errors.
    include: [
      'esptool-js',
      'esptool-js > esp32',
      'esptool-js > esp32c2',
      'esptool-js > esp32c3',
      'esptool-js > esp32c5',
      'esptool-js > esp32c6',
      'esptool-js > esp32c61',
      'esptool-js > esp32h2',
      'esptool-js > esp32p4',
      'esptool-js > esp32s2',
      'esptool-js > esp32s3',
      'esptool-js > esp8266',
    ],
  },
})
