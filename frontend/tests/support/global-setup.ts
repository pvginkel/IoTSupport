import { spawn } from 'node:child_process';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
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

  const seededDbPath = await initializeSeedDatabase();
  process.env.PLAYWRIGHT_SEEDED_SQLITE_DB = seededDbPath;
  console.log(`🗃️  Seeded Playwright SQLite database: ${seededDbPath}`);
  console.log('⏭️  Worker fixtures will boot backend and frontend on demand');
}

export default globalSetup;

async function initializeSeedDatabase(): Promise<string> {
  const repoRoot = getRepoRoot();
  const tmpRoot = await mkdtemp(join(tmpdir(), 'iotsupport-seed-'));
  const dbPath = join(tmpRoot, 'seed.sqlite');
  const scriptPath = resolve(repoRoot, '../backend/scripts/initialize-sqlite-database.sh');

  await runScript(scriptPath, ['--db', dbPath], {
    cwd: repoRoot,
  });

  return dbPath;
}

async function runScript(
  command: string,
  args: readonly string[],
  options: { cwd: string }
): Promise<void> {
  await new Promise<void>((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    if (child.stdout) {
      child.stdout.on('data', chunk => {
        stdout += chunk.toString();
      });
    }
    if (child.stderr) {
      child.stderr.on('data', chunk => {
        stderr += chunk.toString();
      });
    }

    child.on('error', rejectPromise);
    child.on('exit', code => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      const output = [stdout.trim(), stderr.trim()].filter(Boolean).join('\n');
      if (output) {
        console.error(`initialize-sqlite-database.sh failed output:\n${output}`);
      }
      rejectPromise(
        new Error(
          `${command} exited with code ${code ?? 'null'} while initializing Playwright database`
        )
      );
    });
  });
}

let repoRootCache: string | undefined;

function getRepoRoot(): string {
  if (!repoRootCache) {
    const currentDir = dirname(fileURLToPath(import.meta.url));
    repoRootCache = resolve(currentDir, '../..');
  }
  return repoRootCache;
}
