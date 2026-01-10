import createClient from 'openapi-fetch';
import type { paths } from '../../src/lib/api/generated/types';

/**
 * Request wrapper that throws on non-2xx responses
 * @param requestFn - The API request function to execute
 * @returns The response data including possible undefined
 * @throws Error if the request fails
 */
export async function apiRequest<T>(
  requestFn: () => Promise<{ data?: T; error?: unknown; response: Response }>
): Promise<{ data?: T; response: Response }> {
  const { data, error, response } = await requestFn();

  if (error || !response.ok) {
    const errorMessage = typeof error === 'object' && error !== null
      ? (error as { message?: string; detail?: string }).message ||
        (error as { message?: string; detail?: string }).detail ||
        ''
      : '';
    const statusInfo = `${response.status} ${response.statusText}`;
    throw new Error(
      errorMessage
        ? `API request failed: ${statusInfo} - ${errorMessage}`
        : `API request failed: ${statusInfo}`
    );
  }

  return { data, response };
}

/**
 * Creates a typed API client for use in tests.
 * Uses the generated paths type from the OpenAPI spec for full type safety.
 */
export interface CreateApiClientOptions {
  baseUrl?: string;
}

export type ApiClient = ReturnType<typeof createClient<paths>>;

export function createApiClient(options: CreateApiClientOptions = {}): ApiClient {
  const backendUrl = options.baseUrl ?? process.env.BACKEND_URL ?? 'http://localhost:3201';
  return createClient<paths>({
    baseUrl: backendUrl,
    fetch: globalThis.fetch,
  });
}
