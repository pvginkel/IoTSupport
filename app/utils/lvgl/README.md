# LVGL Image Converter

This directory contains the upstream LVGL image conversion module.

## Source

`LVGLImage.py` is a verbatim copy from the official LVGL repository:
https://github.com/lvgl/lvgl/blob/master/scripts/LVGLImage.py

## Maintenance

This file should be kept in sync with the upstream LVGL repository. Any local modifications should be avoided to ensure compatibility with the LVGL project.

To update:
1. Download the latest version from the URL above
2. Replace the existing `LVGLImage.py` file
3. Test the image proxy functionality to ensure compatibility

## Purpose

The `LVGLImage` module provides:
- Conversion of PNG/bitmap images to LVGL binary format
- Support for multiple color formats (ARGB8888, RGB565, etc.)
- Image compression (RLE, LZ4, or none)
- Stride alignment control

This backend uses `LVGLImage` to convert images fetched from external URLs into a format compatible with ESP32 devices running LVGL displays.
