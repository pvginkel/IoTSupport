const DEFAULT_BACKEND_URL = 'http://localhost:5000';

export function getBackendUrl(): string {
  return process.env.BACKEND_URL || DEFAULT_BACKEND_URL;
}

export { DEFAULT_BACKEND_URL };
