# Mouser API Integration - Change Brief

## Overview

Add Mouser API integration as function tools available to the LLM during part analysis. This enables the AI to search Mouser's catalog for parts, retrieve high-quality product images, and extract structured specs from product pages.

## New Function Tools

### 1. SearchMouserByPartNumber
- **Purpose**: Search Mouser by manufacturer part number (MPN)
- **API**: `POST https://api.mouser.com/api/v1/search/partnumber`
- **Availability**: Only when `MOUSER_SEARCH_API_KEY` environment variable is set
- **Input**: Mouser part number or MPN (supports partial matching)
- **Output**: Filtered search results excluding: MouserPartNumber, ProductAttributes, PriceBreaks, ProductCompliance, ImagePath

### 2. SearchMouserByKeyword
- **Purpose**: General keyword search on Mouser
- **API**: `POST https://api.mouser.com/api/v1/search/keyword`
- **Availability**: Only when `MOUSER_SEARCH_API_KEY` environment variable is set
- **Input**: Search keyword string, optional record count and starting record
- **Output**: Same filtered results as part number search

### 3. GetMouserImageFromProductDetailUrl
- **Purpose**: Extract high-quality product image URL from a Mouser product page
- **Availability**: Always (no API key required)
- **Method**: Download the product page HTML and parse the `application/ld+json` script element with `@type: "ImageObject"` to extract the `contentUrl` field
- **User-Agent**: Match what DocumentService uses

### 4. ExtractPartSpecsFromURL
- **Purpose**: Use LLM to extract structured specs from any product page HTML
- **Availability**: Always (no API key required)
- **Method**: Download the URL, pass HTML to LLM with prompt "The following HTML is likely the HTML of an electronics component. Return all specs that are mentioned on the page as JSON."
- **LLM**: Use passed-in AIRunner (same pattern as DuplicateSearchService)

## Prompt Updates

Update `app/services/prompts/part_search.md` with:

1. **Conditional Mouser section** (only when API key is configured):
   - Prefer part number search when input looks like an MPN
   - If input doesn't look like an MPN, do a web search first to determine the MPN, then use part number search
   - Fall back to keyword search if MPN cannot be determined
   - Use `ManufacturerPartNumber` from response (not MouserPartNumber)
   - Set seller as "Mouser" and seller URL as `ProductDetailUrl`
   - Product URL should remain the manufacturer's URL (not Mouser's)
   - Use the image from `GetMouserImageFromProductDetailUrl` as the part image
   - Use `DataSheetUrl` through normal URL classification flow (not treated as magic URL)

2. **Always-present sections** for:
   - `GetMouserImageFromProductDetailUrl` - for extracting high-quality images from Mouser product pages
   - `ExtractPartSpecsFromURL` - for extracting specs from any product page URL

## Caching

Use existing `DownloadCacheService.get_cached_content()` for caching Mouser API responses. This provides 1-day TTL caching based on URL+body hash.

## Error Handling

Return Mouser API errors verbatim in the function response. The LLM will handle errors appropriately.

## Configuration

- New environment variable: `MOUSER_SEARCH_API_KEY`
- Function tools for search are only registered when this key is present
- Prompt instructions for Mouser search are conditionally included via Jinja2 templating

## Files to Create/Modify

1. **New**: `app/utils/ai/mouser_search.py` - Mouser search function implementations
2. **New**: `app/utils/ai/mouser_image.py` - Image URL extraction function
3. **New**: `app/utils/ai/extract_specs.py` - Spec extraction function using LLM
4. **New**: `app/services/mouser_service.py` - Service for Mouser API calls
5. **Modify**: `app/config.py` - Add MOUSER_SEARCH_API_KEY config
6. **Modify**: `app/services/container.py` - Wire up new services and functions
7. **Modify**: `app/services/ai_service.py` - Register new function tools
8. **Modify**: `app/services/prompts/part_search.md` - Add Mouser usage instructions
