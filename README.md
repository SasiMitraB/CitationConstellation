# Citation Constellation

Citation Constellation is a Python tool for building a structured map of how a paper is cited. Instead of a raw count, it shows the sections where citations appear, highlights shared authors, and lets you filter the citation set by topic keywords and author lists. It supports both a CLI (for terminal workflows) and a rich web UI with live progress.

## What It Does

Given a DOI, arXiv ID, ADS URL, or OpenAlex URL/ID, the tool:

1. Resolves the identifier into a canonical paper record.
2. Fetches full metadata and the list of citing papers from ADS or OpenAlex.
3. Downloads arXiv source for each citing paper when available.
4. Locates the bibliography entry that corresponds to the target paper.
5. Parses LaTeX into an AST and extracts the section context for each citation.
6. Renders results as a hierarchical tree in the CLI and as interactive cards in the web UI.

## Key Features

### Multi Source Citation Data

- ADS and OpenAlex support, with automatic fallback between sources.
- Configurable default source and per source settings.
- OpenAlex topics and citation counts included when available.

### Detailed Citation Context

- Finds the exact section, subsection, and subsubsection for each in text citation.
- Handles nested LaTeX and comments using AST parsing (not regex only).
- Includes common citation macros and multiple key citation lists.

### Bibliography Key Resolution

- Scans both .bib and .bbl sources.
- DOI match, title match, and author plus year fallback matching.
- Works with common arXiv submission structures and compiled bibliographies.

### Web UI Workflow With Filters

- Keyword extraction from all citing papers (OpenAlex topics).
- Keyword filter step to narrow the citation set before analysis.
- Author filter step to focus on specific research groups.
- Live progress stream and logs while each citation is processed.
- Summary stats for total citations, citations with context, and unique sections.
- Clickable citation cards with modal paper details (authors, abstract, topics, links).
- Shared author highlighting between the target paper and citing papers.

### CLI Workflow

- Quick, scriptable pipeline for generating a citation tree.
- Optional retention of downloaded sources for inspection.
- Config initialization helper to create a default config file.

## Supported Input Formats

- DOI (example: 10.1038/s41586-020-2649-2)
- arXiv ID (example: 2502.06448)
- ADS URL (example: https://ui.adsabs.harvard.edu/abs/2025arXiv250206448B/abstract)
- OpenAlex URL or ID (example: https://openalex.org/W1234567890 or W1234567890)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure ADS API token (recommended when using ADS):
   ```bash
   export ADS_API_TOKEN="your_token_here"
   ```

3. Configure OpenAlex polite pool email (recommended when using OpenAlex):
   ```bash
   export OPENALEX_POLITE_POOL_EMAIL="your_email@example.com"
   ```

4. Optional: create a config file (recommended for defaults):
   ```bash
   python main.py --init-config
   ```

   This creates ~/.citation_config.yaml which lets you set:
   - default_source (ads or openalex)
   - ADS rate limits and retries
   - OpenAlex polite pool email and rate limits (can reference OPENALEX_POLITE_POOL_EMAIL)

## Usage

### Command Line

Run with an ID or URL:

```bash
python main.py 2502.06448
```

Keep downloaded sources:

```bash
python main.py 2502.06448 --keep-sources
```

Switch data source:

```bash
python main.py 10.1093/mnras/stab1234 --source openalex
```

Initialize config:

```bash
python main.py --init-config
```

### Web Interface

Start the server:

```bash
python app.py
```

Then open http://localhost:5001

Web UI flow:

1. Enter an identifier.
2. Choose a citation source (ADS or OpenAlex).
3. Select keywords from all citing papers (OpenAlex topics).
4. Select authors to further filter the citing set.
5. View live progress and results as cards with citation context.

## How It Works Internally

### Input Resolution (core/resolver.py)

Converts input strings into a PaperID object using regex patterns for DOI, arXiv, ADS, and OpenAlex.

### Metadata and Citation Retrieval (core/fetcher.py, core/openalex_fetcher.py)

- ADS workflow retrieves bibcode, authors, year, DOI, and arXiv ID.
- OpenAlex workflow retrieves topics, citation counts, and abstracts.
- Automatic fallback between ADS and OpenAlex if the preferred source fails.
- Rate limiting and retry behavior are configurable via config.

### Source Download and TeX Entry Point (core/downloader.py)

- Downloads arXiv source tarballs and extracts them to data/extracted.
- Detects the main TeX file by name or by scanning for \documentclass.

### LaTeX Parsing and Context Extraction (core/parser.py)

1. Recursively resolves \input and \include files to build a single TeX stream.
2. Finds the bibliography key that matches the target paper via DOI, title, or author plus year.
3. Builds an AST with pylatexenc and walks the tree to track section headers.
4. Records section, subsection, and subsubsection for each matching \cite macro.

### Output Rendering

- CLI: hierarchical ASCII tree with author, link, topic, and context nodes.
- Web UI: cards with context pills, links, and details in a modal.

## Configuration

The config file at ~/.citation_config.yaml controls:

- default_source: ads or openalex
- ADS: api token, rate limit, retry counts, backoff multiplier
- OpenAlex: polite pool email, rate limit, retry counts, base url

The CLI flag --source overrides the config default for a single run.

## Dependencies

- ads: NASA ADS client
- arxiv: arXiv API wrapper
- bibtexparser: bibliography parsing
- pylatexenc: LaTeX AST parsing
- anytree: CLI tree rendering
- requests: HTTP
- flask: web UI
- pyyaml: configuration

## Project Structure

```
CitationConstellation/
├── main.py              # CLI entry point
├── app.py               # Flask web frontend
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html       # Web UI template
├── static/
│   ├── style.css        # Stylesheet
│   └── app.js           # Client-side JS
└── core/
    ├── author_utils.py  # Author normalization and matching
    ├── config.py        # Configuration management
    ├── downloader.py    # arXiv source download
    ├── fetcher.py       # ADS metadata and citations
    ├── openalex_fetcher.py # OpenAlex metadata and citations
    ├── parser.py        # LaTeX AST and bibliography parsing
    ├── resolver.py      # Input resolution
    └── tree_view.py     # CLI tree rendering
```

## Notes and Limitations

- Full context extraction requires an arXiv source tarball. If a citing paper has no arXiv ID, the tool will still list it but cannot extract section context.
- OpenAlex does not support direct arXiv ID lookup; ADS is preferred for arXiv only inputs.
- Some LaTeX projects have unconventional structures. The main TeX heuristic is robust but not perfect.
- Citation context is based on section headers, not sentence level NLP.

## Troubleshooting

- ADS errors: ensure ADS_API_TOKEN is set and valid.
- OpenAlex warnings: set a real polite pool email in ~/.citation_config.yaml.
- Missing contexts: the citation key could not be resolved or the source does not contain a standard citation macro.
- Slow runs: reduce max_results in config or use author and keyword filters in the web UI.
