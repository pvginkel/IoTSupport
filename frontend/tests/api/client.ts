import createClient from 'openapi-fetch';
import type { paths } from '../../src/lib/api/generated/types';
import type { APIRequestContext } from '@playwright/test';

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
    const errorObj = error as { message?: string; detail?: string; error?: string } | undefined;
    const errorMessage = typeof error === 'object' && error !== null
      ? errorObj?.message || errorObj?.detail || errorObj?.error || JSON.stringify(error)
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
 * Creates a fetch function that wraps Playwright's APIRequestContext.
 * This allows the ApiClient to share cookies with the browser context.
 *
 * Playwright's APIResponse uses methods (.ok(), .status()) while
 * standard Response uses properties (.ok, .status), so we need this adapter.
 */
export function createPlaywrightFetch(requestContext: APIRequestContext): typeof globalThis.fetch {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    // openapi-fetch may pass a Request object as input, so extract URL, method, body, headers from it
    let url: string;
    let method = init?.method ?? 'GET';
    let headers = init?.headers as Record<string, string> | undefined;
    let body = init?.body;

    if (input instanceof Request) {
      url = input.url;
      method = input.method;
      // Clone to read body (can only be read once)
      body = await input.clone().text() || undefined;
      // Extract headers from Request
      const headerObj: Record<string, string> = {};
      input.headers.forEach((value, key) => {
        headerObj[key] = value;
      });
      headers = Object.keys(headerObj).length > 0 ? headerObj : undefined;
    } else if (input instanceof URL) {
      url = input.toString();
    } else {
      url = input;
    }

    const playwrightResponse = await requestContext.fetch(url, {
      method,
      headers,
      data: body,
    });

    // Convert Playwright APIResponse to standard Response
    const status = playwrightResponse.status();

    // 204 No Content responses must have a null body
    // (Response constructor throws if you try to provide a body for 204)
    if (status === 204) {
      return new Response(null, {
        status,
        statusText: playwrightResponse.statusText(),
        headers: Object.fromEntries(
          Object.entries(playwrightResponse.headers())
        ),
      });
    }

    // For other responses, convert Buffer to Uint8Array for compatibility
    const responseBody = await playwrightResponse.body();
    return new Response(new Uint8Array(responseBody), {
      status,
      statusText: playwrightResponse.statusText(),
      headers: Object.fromEntries(
        Object.entries(playwrightResponse.headers())
      ),
    });
  };
}

/**
 * Creates a typed API client for use in tests.
 * Uses the generated paths type from the OpenAPI spec for full type safety.
 */
interface CreateApiClientOptions {
  baseUrl?: string;
  /**
   * Custom fetch function. Use createPlaywrightFetch(page.request) to share
   * cookies with the browser context.
   */
  fetch?: typeof globalThis.fetch;
}

export type ApiClient = ReturnType<typeof createClient<paths>>;

export function createApiClient(options: CreateApiClientOptions = {}): ApiClient {
  const backendUrl = options.baseUrl ?? process.env.BACKEND_URL ?? 'http://localhost:3201';
  return createClient<paths>({
    baseUrl: backendUrl,
    fetch: options.fetch ?? globalThis.fetch,
  });
}
