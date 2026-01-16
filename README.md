# LLMS.txt Generator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-4285F4?logo=google)](https://cloud.google.com/vertex-ai)

Generate [llms.txt](https://llmstxt.org/) files from websites using AI extraction powered by Google Gemini.

<a href="https://buymeacoffee.com/vojtaflorian" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40"></a>

## Features

- **AI-Powered Extraction** - Uses Google Gemini to intelligently extract and structure content
- **Multiple Chunking Strategies** - Single page, pagination, recursive crawling, sitemap parsing
- **Smart Caching** - Avoids redundant fetches with built-in caching
- **CSS Selectors** - Target specific content areas on pages
- **URL Filtering** - Include/exclude patterns for precise control
- **Parallel Processing** - Process multiple pages concurrently
- **Rate Limiting** - Configurable delays to respect server limits
- **Cost Tracking** - Real-time usage and cost estimation

## Quick Start

```bash
# Clone and setup
git clone https://github.com/vojtaflorian/llms-generator.git
cd llms-generator
uv sync

# Configure
cp .env.example .env
# Edit .env: set GOOGLE_CLOUD_PROJECT

# Authenticate
gcloud auth application-default login

# Run
uv run llms-generator
```

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Google Cloud account with Vertex AI enabled

## Installation

```bash
# Install dependencies
uv sync

# Configure credentials
cp .env.example .env
# Edit .env and set GOOGLE_CLOUD_PROJECT

# Authenticate with Google Cloud
gcloud auth application-default login
```

## Usage

### 1. Configure sources

Edit `sources.csv` to define which pages to process:

```csv
id,url,output,chunk_method,chunk_size,prompt_file,enabled,include_pattern,exclude_pattern,content_selector
kontakt,https://example.com/contact,kontakt.md,single,1,default.txt,true,,,
faq,https://example.com/faq,faq.md,single,1,default.txt,true,,,.faq-content
docs,https://example.com/docs,docs.md,recursive,10,default.txt,true,,,.main-content
```

### 2. Run generator

```bash
# Process all enabled sources
uv run llms-generator

# Process specific sources only
uv run llms-generator --only=kontakt,faq

# Force re-fetch (ignore cache)
uv run llms-generator --force

# Dry run (no AI calls)
uv run llms-generator --dry-run

# Verbose output
uv run llms-generator -v

# Parallel processing with custom workers
uv run llms-generator --workers=10

# Sequential processing
uv run llms-generator --no-parallel

# Custom rate limiting (seconds between requests)
uv run llms-generator --rate-limit=2.0
```

### 3. Deploy

Upload contents of `output/` directory to your web server:
- `llms.txt` → root of website (e.g., `https://example.com/llms.txt`)
- `llms/*.md` → `/llms/` directory (e.g., `https://example.com/llms/kontakt.md`)

## Configuration

### Environment Variables (.env)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes | - | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | No | `europe-west1` | GCP region |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Model (gemini-2.5-flash, gemini-1.5-pro, ...) |
| `MAX_CONTENT_LENGTH` | No | `100000` | Max characters sent to AI |
| `SITE_NAME` | No | `Website` | Site name for llms.txt header |
| `SITE_DESCRIPTION` | No | - | Manual site description |
| `SITE_ABOUT_URL` | No | - | URL for auto-generating site description |

### sources.csv Columns

| Column | Description | Required |
|--------|-------------|----------|
| `id` | Unique source identifier | Yes |
| `url` | Source URL (or sitemap.xml for sitemap method) | Yes |
| `output` | Output filename (saved to output/llms/) | Yes |
| `chunk_method` | Processing strategy (see below) | Yes |
| `chunk_size` | Max pages/items to process | Yes |
| `prompt_file` | AI prompt template file (in prompts/) | Yes |
| `enabled` | `true`/`false` to enable/disable | Yes |
| `include_pattern` | Glob pattern for URLs to include | No |
| `exclude_pattern` | Glob pattern for URLs to exclude | No |
| `content_selector` | CSS selector for main content | No |

### Chunk Methods

| Method | Description | chunk_size | Best For |
|--------|-------------|------------|----------|
| `single` | Single page as one chunk | ignored | Contact, About pages |
| `paginated` | Follow pagination links | max pages | Product listings, archives |
| `recursive` | Crawl internal links | max subpages | Documentation, categories |
| `alphabetical` | Split by first letter | items per chunk | Glossaries, dictionaries |
| `sitemap` | Parse sitemap.xml | max URLs | Large sites |

## Custom Prompts

Create custom prompts in `prompts/` directory. Use `{content}` placeholder for page content.

Example `prompts/faq.txt`:
```
Extract FAQ items from this page.

Format as Markdown:
## [Category]
### [Question]
[Answer]

Content:
{content}
```

## Output Structure

```
output/
├── llms.txt           # Main index file (deploy to site root)
└── llms/              # Content files (deploy to /llms/)
    ├── kontakt.md
    ├── faq.md
    └── ...
```

## Project Structure

```
llms-generator/
├── pyproject.toml      # Dependencies & project config
├── sources.csv         # Source configuration
├── .env                # Environment config (not in git)
├── .env.example        # Environment template
├── prompts/            # AI prompt templates
├── src/llms_generator/ # Source code
├── output/             # Generated files (not in git)
├── cache/              # Cached pages (not in git)
└── README.md
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

If you find this project useful, consider buying me a coffee!

<a href="https://buymeacoffee.com/vojtaflorian" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50"></a>
