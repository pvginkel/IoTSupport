# Change Brief: LVGL Image Proxy

## Summary

Add an API endpoint that fetches images from external URLs, optionally resizes them, and converts them to LVGL binary format for ESP32 devices with LVGL displays.

## Functional Requirements

### Endpoint Behavior

`GET /api/images/lvgl` with the following query parameters:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | The external URL to fetch the image from |
| `headers` | No | Comma-separated list of header names to forward from the request to the external URL (for authentication) |
| `width` | No | Target width in pixels |
| `height` | No | Target height in pixels |

### Processing Pipeline

1. **Header forwarding**: For each header name in the `headers` parameter, read the corresponding header from the incoming request and forward it to the external URL (e.g., for Home Assistant authentication tokens).

2. **Image fetch**: Retrieve the image from the external URL using the forwarded headers.

3. **Resize** (if width/height specified): Resize the image while maintaining aspect ratio. Only downsize - if the image is smaller than the target dimensions, don't upscale. When both width and height are specified, fit within the bounds while preserving aspect ratio.

4. **Convert to LVGL format**: Convert the image to LVGL binary format (ARGB8888) using the upstream `LVGLImage.py` script from the LVGL project.

5. **Return binary**: Return the LVGL binary data with appropriate content type.

### LVGLImage.py Integration

- The `LVGLImage.py` file must be kept as a verbatim copy from https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py
- Place it in `app/utils/lvgl/LVGLImage.py`
- Include a `README.md` in that folder documenting the source
- Import and use the `LVGLImage` and `ColorFormat` classes directly (no subprocess calls)

### Error Handling

- Return 400 if required `url` parameter is missing
- Return 400 if a header specified in `headers` is not present in the request
- Return 502 if the external URL fetch fails
- Return 500 if image processing or conversion fails

### Response Headers

- Set `Cache-Control: no-store` to prevent caching (images may change frequently)
- Set appropriate `Content-Type` for binary data

## Dependencies

New Python packages required:
- `pypng` - PNG encoding/decoding for LVGLImage.py
- `lz4` - Compression support for LVGLImage.py
- `Pillow` - Image resizing (replacing PHP's GD library)
- `httpx` or `requests` - HTTP client for fetching external images

## Out of Scope

- Caching of fetched/converted images
- Rate limiting
- Image format detection/validation beyond what Pillow handles
- Support for color formats other than ARGB8888 (can be added later)
