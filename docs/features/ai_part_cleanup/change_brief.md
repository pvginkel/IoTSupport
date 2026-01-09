# Change Brief: AI Part Cleanup

## Summary

Add a new long-running task that uses AI to clean up and improve existing parts in the inventory. This complements the existing AI analysis feature (used for new parts) by applying current AI analysis rules to potentially older data that was entered before certain tools or rules were available.

## Functional Requirements

### Input
- Part key (4-character ID) identifying the part to clean up

### AI Context Provided
1. **Developer prompt**: A modified version of the existing `part_search.md` prompt, using Jinja2 conditionals to customize behavior for cleanup mode vs. analysis mode. The prompt should:
   - Instruct the AI that its job is to improve data quality by applying current rules to potentially old data
   - Assume that some tools may not have been available when the part was originally created
   - Emphasize that data should not be lost during cleanup

2. **All existing parts** (except the target part): Provided as JSON to show the AI how parts are currently formatted, ensuring consistency. Each part includes:
   - `key`, `manufacturer_code`, `type`, `description`, `manufacturer`, `tags`
   - `package`, `pin_count`, `pin_pitch`, `voltage_rating`, `input_voltage`, `output_voltage`, `mounting_type`, `series`, `dimensions`
   - `product_page`, `seller` (name), `seller_link`

3. **The target part**: Same JSON structure as above

### AI Tools Available
- URLClassifierFunction (classify URLs as pdf, image, webpage, or invalid)
- AI model's inherent web search capabilities (can query Mouser, Digi-Key, and other sites)

### AI Tools NOT Available
- Duplicate search function (explicitly excluded from cleanup mode)

### Output
- The complete part data in the same structure as the input, with fields modified as the AI sees fit
- Returned verbatim over SSE as the task result
- The UI will handle showing a diff and helping the user apply changes

### Fields That Should NOT Be Changed
- `created_at` / `updated_at`
- Part locations
- Quantity history
- Kit contents
- Attachment set (no new images or datasheets expected)

### Fields That SHOULD Be Analyzed
- All fields listed in the "All existing parts" context above
- Specifically: `product_page`, `seller`, `seller_link` are in scope

## Technical Approach

1. **Prompt file**: Rename `part_search.md` to something more general (e.g., `part_analysis.md`) and add Jinja2 conditionals for `{% if mode == 'cleanup' %}` vs `{% if mode == 'analysis' %}` sections.

2. **New task class**: Similar to `AIPartAnalysisTask`, but:
   - Accepts part key as input
   - Fetches all parts for context
   - Uses cleanup mode for prompt rendering
   - Returns the complete improved part data

3. **New service method**: In `AIService`, add a method for cleanup that:
   - Builds the context with all parts
   - Renders the prompt in cleanup mode
   - Excludes duplicate search function
   - Returns the improved part JSON

4. **New API endpoint**: `POST /ai-parts/cleanup` to start the cleanup task, similar to existing `/ai-parts/analyze`

## Out of Scope
- Applying the changes to the database (UI handles this)
- Before/after diff generation (UI handles this)
- Batch cleanup of multiple parts
