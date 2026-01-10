import { createRouter, RouterProvider } from '@tanstack/react-router'

// Import the generated route tree
import { routeTree } from './routeTree.gen'
import { isTestMode } from '@/lib/config/test-mode'
import { setupRouterInstrumentation } from '@/lib/test/router-instrumentation'

// Create a new router instance
const router = createRouter({ routeTree })

// Setup router instrumentation in test mode
if (isTestMode()) {
  setupRouterInstrumentation(router)
}

// Register the router instance for type safety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

function App() {
  return <RouterProvider router={router} />
}

export default App
