/**
 * Monaco Editor JSON schema validation utilities.
 * Configures Monaco's JSON language service to validate against provided JSON schemas.
 *
 * IMPORTANT: For schema validation and autocomplete to work, the Editor component
 * must have a `path` prop that matches the `modelPath` passed to this function.
 * Example: <Editor path="device-config.json" ... />
 */

// Monaco global type for runtime access
interface MonacoGlobal {
  languages: {
    json: {
      jsonDefaults: {
        setDiagnosticsOptions: (options: {
          validate?: boolean;
          schemaValidation?: 'error' | 'warning' | 'ignore';
          enableSchemaRequest?: boolean;
          schemas?: Array<{
            uri: string;
            fileMatch?: string[];
            schema?: Record<string, unknown>;
          }>;
        }) => void;
      };
    };
  };
}

// Track current schema configuration to detect changes
let currentSchemaHash: string | null = null

/**
 * Simple hash function for schema comparison
 */
function hashSchema(schema: Record<string, unknown>): string {
  return JSON.stringify(schema)
}

/**
 * Configure Monaco editor for JSON schema validation and autocomplete.
 * Sets up the JSON language service with a schema for validation and IntelliSense.
 *
 * @param schema - JSON Schema object to validate against
 * @param modelPath - The path used in the Editor's `path` prop (e.g., 'device-config.json')
 *
 * @example
 * ```tsx
 * // In component:
 * <Editor
 *   path="device-config.json"  // Must match modelPath below
 *   defaultLanguage="json"
 *   ...
 * />
 *
 * // Configure schema:
 * useEffect(() => {
 *   if (configSchema) {
 *     configureMonacoSchemaValidation(configSchema, 'device-config.json')
 *   }
 * }, [configSchema])
 * ```
 */
export function configureMonacoSchemaValidation(
  schema: Record<string, unknown>,
  modelPath: string
): void {
  // Monaco and its JSON language service are loaded async, need to access via the global
  const monaco = (window as unknown as { monaco?: MonacoGlobal }).monaco
  if (!monaco) {
    // Monaco not yet loaded, editor will work without validation
    return
  }

  // Check if schema has changed
  const schemaHash = hashSchema(schema)
  if (currentSchemaHash === schemaHash) {
    return
  }

  // The schema URI is just an identifier for Monaco's internal use
  const schemaUri = `inmemory://schema/config-schema.json`

  // Configure the JSON language service with the schema
  // fileMatch must match the `path` prop on the Editor component
  monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
    validate: true,
    schemaValidation: 'error',
    enableSchemaRequest: false,
    schemas: [
      {
        uri: schemaUri,
        fileMatch: [modelPath],
        schema: {
          ...schema,
          // Ensure schema has required $schema if not present
          $schema: schema.$schema ?? 'http://json-schema.org/draft-07/schema#',
        },
      },
    ],
  })

  currentSchemaHash = schemaHash
}

/**
 * Clear all configured schemas.
 * Useful when navigating away or when schemas need to be refreshed.
 */
export function clearMonacoSchemas(): void {
  const monaco = (window as unknown as { monaco?: MonacoGlobal }).monaco
  if (!monaco) {
    return
  }

  // Reset to default diagnostics options (no custom schemas)
  monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
    validate: true,
    schemaValidation: 'error',
    enableSchemaRequest: false,
    schemas: [],
  })

  currentSchemaHash = null
}
