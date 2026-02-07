# Citation Constellation

A Python-based tool designed to visualize the "constellation" of citations for a scientific paper. It goes beyond simple citation counts by analyzing the *context* in which a paper is cited.

It works by:
1.  Identifying a target paper.
2.  Finding papers that cite it.
3.  Downloading the LaTeX source code of those citing papers (from arXiv, upto 25 citing papers).
4.  Parsing the source code to find the exact section and subsection where the citation occurs.
5.  Displaying a hierarchical tree of this information.

## Technical Implementation & Workflow

The project is modularized into a `core` package. Here is how each step works internally:

### 1. Input Resolution (`core/resolver.py`)
The tool accepts various input formats:
- **DOI** (e.g., `10.1038/s41586-020-2649-2`)
- **ArXiv ID** (e.g., `2502.06448`)
- **NASA ADS URL** (e.g., `https://ui.adsabs.harvard.edu/abs/2025arXiv250206448B/abstract`)

It uses regex patterns to identify the input type and normalizes it into a `PaperID` object.

### 2. Metadata & Citation Retrieval (`core/fetcher.py`)
This module interacts with the **NASA ADS API** (Astrophysics Data System).
- **Metadata**: It queries ADS to get the Bibcode, Title, Authors, Year, and DOI of the target paper.
- **Citations**: It queries ADS for papers *citing* the target bibcode.
- **Robustness**: 
    - Implements **Rate Limiting** (1s delay between calls).
    - Implements **Exponential Backoff** for 503 Service Unavailable errors.
    - Fallback: If ADS fails to resolve an ArXiv ID, it attempts to use the `arxiv` Python library as a backup for basic metadata.

### 3. Source Code Retrieval (`core/downloader.py`)
To analyze *where* a paper is cited, we need its full text source.
- The tool checks if the citing paper has an **ArXiv ID**.
- It uses the `arxiv` library to download the source tarball (`.tar.gz`).
- It extracts the tarball to a temporary directory `data/extracted/{arxiv_id}`.
- **Main TeX Identification**: It heuristically finds the main LaTeX file by looking for files containing `\documentclass`.

### 4. LaTeX Parsing & Analysis (`core/parser.py`)
This is the most complex part of the system.

#### A. Citation Key Resolution
Before we can find the citation in the text, we must know *what key* the author used to cite our target paper (e.g., `Smith2023` or `b12`).
The tool scans the downloaded source directory for bibliography files:
1.  **`.bib` Files**: Standard BibTeX files. It parses them using `bibtexparser`.
2.  **`.bbl` Files**: Compiled bibliographies (common in arXiv uploads). It parses `\bibitem{key}` entries using regex.

**Matching Logic**: To find the correct key, it compares the bibliography entry against our target paper's metadata using three strategies:
1.  **DOI Match**: Checks if the target DOI appears in the entry.
2.  **Title Match**: fuzzy matches the target title against the entry text.
3.  **Author + Year Match**: (Robust fallback) Checks if the First Author's last name and the Publication Year appear in the entry text.

#### B. AST Construction
It uses `pylatexenc.latexwalker` to generate an **Abstract Syntax Tree (AST)** of the LaTeX code. This allows for robust parsing that handles nested braces, environments, and comments better than regex.

#### C. Context Extraction
It traverses the AST, maintaining a "state" of the current Section, Subsection, and Subsubsection.
- When it encounters a citation macro (e.g., `\cite{key}`, `\citep{key}`), it checks if the key matches the resolved key from Step 4A.
- If it matches, it records the current Section/Subsection context.

### 5. Reporting (`core/tree_view.py`)
The results are rendered into a hierarchical ASCII tree using the `anytree` library.
The output structure is:
- **Root**: Target Paper
    - **Child**: Citing Paper Title
        - **Info**: Authors
        - **Info**: Link (ArXiv/DOI)
        - **Context**: "Introduction", "Methods > Analysis", etc.

## dependencies

- **`ads`**: Official Python client for NASA ADS API.
- **`arxiv`**: Wrapper for the arXiv API.
- **`pylatexenc`**: A robust LaTeX parser for Python.
- **`bibtexparser`**: For parsing `.bib` files.
- **`anytree`**: For generating the tree visualization.
- **`requests`**: For general HTTP requests.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **ADS API Token**:
        You need an API token from [NASA ADS](https://ui.adsabs.harvard.edu/).
        - Set it as an environment variable:
            ```bash
            export ADS_API_TOKEN="your_token_here"
            ```
        - To persist it, add the export line to your shell profile (e.g., `~/.zshrc`).

## Usage

### Command Line

```bash
# Using an ArXiv ID (Source files are deleted automatically after run)
python main.py 2502.06448

# To KEEP the downloaded source files for inspection:
python main.py 2502.06448 --keep-sources
```

### Web Interface

```bash
python app.py
```

Then open [http://localhost:5001](http://localhost:5001) in your browser. The web UI provides:
- live progress streaming as each citation is processed
- a visual summary of citing papers with section-level context
- clickable links to arXiv, DOI, and ADS for every paper

## Project Structure

```
CitationConstellation/
├── main.py              # CLI entry point
├── app.py               # Flask web frontend
├── requirements.txt     # Python dependencies
├── data/                # Downloaded and extracted source files
├── templates/
│   └── index.html       # Web UI template
├── static/
│   ├── style.css        # Stylesheet
│   └── app.js           # Client-side JS
└── core/
    ├── resolver.py      # input -> PaperID
    ├── fetcher.py       # ADS API interaction
    ├── downloader.py    # ArXiv source download
    ├── parser.py        # LaTeX AST and Bibliography parsing
    └── tree_view.py     # Hierarchical output generation
```
