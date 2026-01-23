/**
 * Monaco Editor JSON schema validation utilities.
 * Configures Monaco's JSON language service to validate against provided JSON schemas.
 */

// Monaco global type for runtime access
interface MonacoGlobal {
  languages: {
    json: {
      jsonDefaults: {
        setDiagnosticsOptions: (options: {
          validate?: boolean;
          schemaValidation?: 'error' | 'warning' | 'ignore';
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

// Monaco editor type for function parameters
interface MonacoEditorInstance {
  getModel: () => {
    uri: {
      toString: () => string;
    };
  } | null;
}

// Track configured schemas by URI to avoid duplicates
const configuredSchemas = new Map<string, boolean>()

/**
 * Configure Monaco editor for JSON schema validation.
 * Sets up the JSON language service with a schema for validation and IntelliSense.
 *
 * @param editorInstance - Monaco editor instance
 * @param schema - JSON Schema object to validate against
 * @param schemaId - Unique identifier for the schema (used in the schema URI)
 *
 * @example
 * ```tsx
 * const handleEditorMount = (editor) => {
 *   if (configSchema) {
 *     configureMonacoSchemaValidation(editor, configSchema, 'device-config')
 *   }
 * }
 * ```
 */
export function configureMonacoSchemaValidation(
  editorInstance: unknown,
  schema: Record<string, unknown>,
  schemaId: string
): void {
  // Type guard for Monaco editor instance
  const isMonacoEditor = (obj: unknown): obj is MonacoEditorInstance =>
    obj !== null &&
    typeof obj === 'object' &&
    'getModel' in obj &&
    typeof (obj as MonacoEditorInstance).getModel === 'function'

  if (!isMonacoEditor(editorInstance)) {
    return
  }

  // Monaco and its JSON language service are loaded async, need to access via the global
  const monaco = (window as unknown as { monaco?: MonacoGlobal }).monaco
  if (!monaco) {
    // Monaco not yet loaded, editor will work without validation
    return
  }

  const schemaUri = `inmemory://schema/${schemaId}.json`
  const modelUri = editorInstance.getModel()?.uri.toString() ?? ''

  // Skip if schema already configured for this URI
  if (configuredSchemas.has(schemaUri)) {
    return
  }

  // Configure the JSON language service with the schema
  monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
    validate: true,
    schemaValidation: 'error',
    schemas: [
      {
        uri: schemaUri,
        fileMatch: [modelUri, '*.json'],
        schema: {
          ...schema,
          // Ensure schema has required $schema if not present
          $schema: schema.$schema ?? 'http://json-schema.org/draft-07/schema#',
        },
      },
    ],
  })

  configuredSchemas.set(schemaUri, true)
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
    schemas: [],
  })

  configuredSchemas.clear()
}
