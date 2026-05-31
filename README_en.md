<p align="center">
  <span>English</span> | <a href="./README.md">简体中文</a>
</p>

<div align="center">

# Album Assetizer

**Personal Album Semantic Asset Generator · Turn photos into searchable structured data**

<p>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  </a>
  <a href="https://github.com/SeanWong17/album-assetizer/pulls">
    <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome">
  </a>
</p>

<img src="docs/screenshots/Demo.png" alt="Preview" width="80%">

</div>

---

## Overview

Tens of thousands of photos on your phone, yet finding a specific one means scrolling endlessly. Built-in album search is limited, and your data is locked inside vendor ecosystems.

**Album Assetizer** scans local photo albums, calls vision LLMs to generate structured descriptions for each image (scene, tags, subjects, activities, OCR, etc.), extracts EXIF timestamps and GPS coordinates, and outputs everything in standard formats (JSONL / CSV / SQLite) ready for any downstream application.

```
Photos → Scan → EXIF extraction → Vision LLM annotation → Structured data assets
```

---

## Key Features

| Module | Description |
|--------|-------------|
| **Format Support** | JPG / PNG / HEIC / DNG / CR3 / LIVP (Apple Live Photo) |
| **Image Preprocessing** | Auto-resize, EXIF orientation fix, RGBA→RGB, RAW decode, size control |
| **Metadata Extraction** | EXIF capture time, GPS coordinates, timezone parsing |
| **LLM Annotation** | OpenAI-compatible API, Structured Output (json_schema + auto-fallback) |
| **Concurrency** | Multi-threaded + RPM rate limiting + auto scale-up + auto scale-down |
| **Fault Tolerance** | Exponential backoff, error classification, crash recovery, graceful shutdown |
| **Two-pass Refinement** | First-pass vision + optional text-model refinement for consistency |
| **Data Export** | SQLite persistence, one-click JSONL / CSV / failure list export |
| **Quality Review** | Built-in HTML review script with pagination, filtering, keyboard navigation |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/SeanWong17/album-assetizer.git
cd album-assetizer
pip install -e .
```

### 2. Configure API

```bash
mkdir -p /path/to/album/.album-assetizer
cp examples/sample.env /path/to/album/.album-assetizer/.env
```

Edit the `.env` file with your API credentials (any OpenAI-compatible endpoint):

```env
ALBUM_ASSETIZER_API_KEY=your_api_key
ALBUM_ASSETIZER_BASE_URL=https://your-provider.com/v1
ALBUM_ASSETIZER_MODEL=your-vision-model
```

### 3. Verify Connectivity

```bash
album-assetizer --root /path/to/album smoke-text
album-assetizer --root /path/to/album smoke-image --path some_photo.jpg
```

### 4. Run the Full Pipeline

```bash
album-assetizer --root /path/to/album scan            # Discover assets
album-assetizer --root /path/to/album sync-metadata   # Extract EXIF time/GPS
album-assetizer --root /path/to/album run             # LLM annotation
album-assetizer --root /path/to/album export          # Export JSONL/CSV
album-assetizer --root /path/to/album stats           # View statistics
```

---

## Output Fields

Each image produces a structured record:

| Field | Type | Description |
|-------|------|-------------|
| `caption_short` | string | One-line summary |
| `caption_long` | string | Detailed description for retrieval |
| `scene` | string | Scene classification |
| `tags` | list | Semantic tags (6-18, deduplicated) |
| `main_subjects` | list | Primary subjects in the image |
| `activities` | list | Ongoing activities |
| `style_labels` | list | Style labels (screenshot, B&W, HDR, etc.) |
| `quality_flags` | list | Quality markers (blurry, overexposed, etc.) |
| `safety_flags` | list | Safety markers |
| `contains_text` | bool | Whether the image contains readable text |
| `ocr_text` | string | Extracted text (≤300 chars) |
| `people_count` | int | Number of people (-1 if uncertain) |
| `confidence` | float | Annotation confidence (0-1) |
| `embedding_text` | string | Concatenated text for embedding |
| `taken_at` | string | EXIF capture time (ISO 8601) |
| `gps_lat` / `gps_lng` | float | EXIF GPS coordinates |

---

## Project Scope

This project focuses solely on **generating and persisting high-quality semantic assets from photo albums**.

A lightweight review script is included (shown in the screenshot above) for browsing images alongside their structured descriptions to verify annotation quality. More complete consumption scenarios (search, clustering, recommendations, timeline, map visualization) are out of scope — you can plug the data into whatever toolchain works for you.

---

## License

[MIT License](LICENSE) © 2026 SeanWong17

---

<div align="center">
  <br>
  Made with ❤️ by <a href="https://github.com/SeanWong17">SeanWong17</a>
</div>
