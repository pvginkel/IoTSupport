# Change Brief: Datasheet Spec Extraction AIFunction

## Summary

Add a new AIFunction called `extract_specs_from_datasheet` that extracts technical specifications from a PDF datasheet using AI. This function will be called by the main part analysis LLM when it has identified a datasheet URL.

## Functional Requirements

### New AIFunction: `extract_specs_from_datasheet`

**Request Model:**
- `analysis_query` (string): Free-text description of the part being analyzed. Used to validate that the datasheet matches what we're looking for. The main LLM provides context about which part we're searching for.
- `datasheet_url` (string): URL to a PDF document containing the datasheet.

**Response Model:**
- `specs` (optional): Full `PartAnalysisDetails` DTO with extracted specifications (package_type, mounting_type, pin_count, pin_pitch, voltages, dimensions, plus identification fields if found with confidence).
- `error` (optional): Explanation of why extraction failed (e.g., datasheet doesn't match the analysis query, PDF unreadable, etc.).

### Implementation Details

1. **URL Validation**: Use `DocumentService.process_upload_url` to validate the URL is a PDF and can be downloaded.

2. **PDF Handling**: Send the full PDF bytes to OpenAI API:
   - Upload file with `client.files.create(file=..., purpose="assistants")`
   - Include in user message as `{"type": "input_file", "file_id": pdf_file.id}`
   - Delete uploaded file in a finally block using `client.files.delete()`

3. **AIRequest Extension**: Add attachment support to `AIRequest` - a list of file paths that get uploaded and included in the request.

4. **OpenAIRunner Extension**: Implement PDF upload and attachment handling in the runner.

5. **Prompt**: Create `app/services/prompts/spec_extraction.md` - an abstract of `part_analysis.md` containing:
   - Spec field normalization rules (package_type, mounting_type, voltages, dimensions, etc.)
   - Instructions to validate the datasheet matches the analysis query
   - Instructions to return specs only if confident the datasheet is correct

6. **Main Prompt Update**: Extend `app/services/prompts/part_analysis.md` to:
   - Instruct the LLM to prioritize getting a datasheet for specs over web search
   - Once a verified datasheet URL is found, call `extract_specs_from_datasheet`
   - Prioritize this function over attempting to get specs from the internet

7. **Metrics**: Add Prometheus metrics tracking:
   - Request count by outcome (success/error/validation_failed)
   - Duration
   - Token usage

8. **Wiring**: Register the new function in the service container and wire it into `AIService`.

## Out of Scope

- ClaudeRunner PDF support (will be removed)
- Page limits or size restrictions on PDFs
- Merging logic for extracted specs (left to main LLM)
