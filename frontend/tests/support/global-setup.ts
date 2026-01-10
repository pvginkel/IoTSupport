import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

async function globalSetup() {
  // Load test environment variables
  config({ path: resolve(__dirname, '../../.env.test') });

  // External services mode is not supported - all tests use per-worker managed services
  if (process.env.PLAYWRIGHT_MANAGED_SERVICES === 'false') {
    throw new Error(
      'PLAYWRIGHT_MANAGED_SERVICES=false is no longer supported. ' +
        'All tests use per-worker managed services (backend and frontend) for isolation. ' +
        'Please remove this environment variable.'
    );
  }

  console.log('🔧 Setting up Playwright tests...');
  console.log('Service management: Per-worker (Playwright managed)');
  console.log('⏭️  Worker fixtures will boot backend and frontend on demand');
}

export default globalSetup;
