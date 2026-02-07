"""
Citation Constellation — Flask Web Frontend

Run with:  python app.py
Then open: http://localhost:5001
"""

import os
import sys
import json
import uuid
import shutil
import threading
import queue
import time
from flask import Flask, render_template, request, jsonify, Response

from core.resolver import resolve_paper_id
from core.fetcher import get_paper_metadata_multi_source, get_citations_multi_source
from core.config import load_config, get_default_source
from core.downloader import download_source, extract_source, find_main_tex
from core.parser import get_ast, find_citations as find_cite_contexts, find_key_for_paper, resolve_latex_inclusions
from core.author_utils import find_shared_authors

app = Flask(__name__)

# Load configuration at startup
APP_CONFIG = load_config()
DEFAULT_SOURCE = get_default_source(APP_CONFIG)

# ---------------------------------------------------------------------------
# In-memory job store  (sufficient for a single-user local tool)
# ---------------------------------------------------------------------------
jobs = {}          # job_id -> {status, result, progress_queue}

class Job:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.status = "running"   # running | done | error
        self.result = None
        self.error = None
        self.queue = queue.Queue()

    def send(self, event, data):
        """Push a server-sent event into the queue."""
        self.queue.put({"event": event, "data": data})

    def finish(self, result):
        self.result = result
        self.status = "done"
        self.send("done", result)

    def fail(self, message):
        self.error = message
        self.status = "error"
        self.send("error", {"message": message})


def _serialize_paper(paper, root_authors=None):
    """
    Serialize a paper to a JSON-friendly dict.
    Optionally compare against root_authors to identify shared authors.
    """
    shared_authors = []
    if root_authors:
        shared_authors = find_shared_authors(root_authors, paper.authors)

    return {
        "title": paper.title,
        "authors": paper.authors[:5] if paper.authors else [],
        "authors_truncated": len(paper.authors) > 5 if paper.authors else False,
        "shared_authors": shared_authors[:5],
        "has_shared_authors": len(shared_authors) > 0,
        "year": paper.year,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "bibcode": paper.bibcode,
        "openalex_id": getattr(paper, 'openalex_id', None),
        "topics": getattr(paper, 'topics', []),
        "cited_by_count": getattr(paper, 'cited_by_count', None),
        "source": getattr(paper, 'source', None),
        "abstract": getattr(paper, 'abstract', None),
    }


def _extract_keywords_from_papers(papers):
    """
    Extract all unique keywords/topics from a list of papers.
    Returns a dict of {keyword: count} sorted by frequency.
    """
    keyword_counts = {}
    for paper in papers:
        # Get topics from OpenAlex papers
        if hasattr(paper, 'topics') and paper.topics:
            for topic in paper.topics:
                keyword = topic.get('display_name', '')
                if keyword:
                    keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

    # Sort by count descending, then alphabetically
    sorted_keywords = sorted(keyword_counts.items(), key=lambda x: (-x[1], x[0]))
    return {k: v for k, v in sorted_keywords}


def _extract_authors_from_papers(papers):
    """
    Extract all unique authors from papers and count occurrences.
    Uses normalize_author_name() to handle name format variations.
    Returns list of (author_name, count) tuples sorted by count (descending).
    """
    from core.author_utils import normalize_author_name

    author_counts = {}

    for paper in papers:
        if hasattr(paper, 'authors') and paper.authors:
            for author_name in paper.authors:
                # Normalize author name to handle format variations
                normalized = normalize_author_name(author_name)
                if normalized:  # Only count if normalization successful
                    author_counts[normalized] = author_counts.get(normalized, 0) + 1

    # Sort by count (descending), then alphabetically
    sorted_authors = sorted(author_counts.items(), key=lambda x: (-x[1], x[0]))
    return sorted_authors


def _serialize_contexts(contexts):
    """Turn a list of CitationContext | str into JSON-friendly dicts."""
    out = []
    for ctx in contexts:
        if isinstance(ctx, str):
            out.append({"type": "status", "text": ctx})
        else:
            out.append({
                "type": "context",
                "section": ctx.section,
                "subsection": ctx.subsection,
                "subsubsection": ctx.subsubsection,
                "label": repr(ctx),
            })
    return out


# ---------------------------------------------------------------------------
# Background worker — mirrors main.py logic but pushes progress events
# ---------------------------------------------------------------------------
def _run_job(job, input_str, keep_sources, source, selected_keywords=None, selected_authors=None):
    try:
        # 1. Resolve input
        job.send("log", f"Resolving input: {input_str}")
        paper_id = resolve_paper_id(input_str)
        job.send("log", f"Resolved to: {paper_id}")

        # 2. Metadata
        job.send("log", f"Fetching metadata from {source.upper()}…")
        root_metadata = get_paper_metadata_multi_source(paper_id, preferred_source=source)
        job.send("log", f"Target paper: {root_metadata.title}")
        job.send("root", _serialize_paper(root_metadata))

        if not root_metadata.bibcode and source == 'ads':
            job.send("log", "⚠ No bibcode — citation queries may fail.")

        # 3. Citations
        job.send("log", "Fetching all citing papers…")
        citing_papers = get_citations_multi_source(root_metadata, preferred_source=source)
        job.send("log", f"Found {len(citing_papers)} citing papers.")

        # 4. Filter by keywords if specified
        if selected_keywords and len(selected_keywords) > 0:
            job.send("log", f"Filtering by keywords: {', '.join(selected_keywords)}")
            filtered_papers = []
            for paper in citing_papers:
                # Check if paper has any of the selected keywords
                if hasattr(paper, 'topics') and paper.topics:
                    paper_keywords = {t.get('display_name', '') for t in paper.topics}
                    if any(kw in paper_keywords for kw in selected_keywords):
                        filtered_papers.append(paper)
            citing_papers = filtered_papers
            job.send("log", f"After keyword filtering: {len(citing_papers)} papers.")

        # 5. Filter by authors if specified
        if selected_authors and len(selected_authors) > 0:
            from core.author_utils import normalize_author_name
            job.send("log", f"Filtering by authors: {', '.join(selected_authors)}")
            filtered_papers = []
            for paper in citing_papers:
                if hasattr(paper, 'authors') and paper.authors:
                    paper_normalized_authors = {normalize_author_name(a) for a in paper.authors if a}
                    if any(author in paper_normalized_authors for author in selected_authors):
                        filtered_papers.append(paper)
            citing_papers = filtered_papers
            job.send("log", f"After author filtering: {len(citing_papers)} papers.")

        job.send("total", len(citing_papers))

        citation_count = 0

        for i, citing_paper in enumerate(citing_papers):
            idx = i + 1
            job.send("progress", {
                "current": idx,
                "total": len(citing_papers),
                "title": citing_paper.title,
            })
            job.send("log", f"[{idx}/{len(citing_papers)}] {citing_paper.title}")

            if not citing_paper.arxiv_id:
                job.send("log", "  → No arXiv ID, skipping source analysis.")
                citation_data = {
                    "paper": _serialize_paper(citing_paper, root_authors=root_metadata.authors),
                    "citations": [{"type": "status", "text": "Source not available"}],
                }
                job.send("paper", citation_data)
                citation_count += 1
                continue

            try:
                tar_path = download_source(citing_paper.arxiv_id, output_dir="data/sources")
                extract_dir = extract_source(tar_path, extract_to=f"data/extracted/{citing_paper.arxiv_id}")

                main_tex = find_main_tex(extract_dir)
                with open(main_tex, "r", errors="replace") as f:
                    raw_tex = f.read()
                tex_content = resolve_latex_inclusions(extract_dir, raw_tex)

                citation_key = find_key_for_paper(
                    extract_dir,
                    target_doi=root_metadata.doi,
                    target_title=root_metadata.title,
                    target_authors=root_metadata.authors,
                    target_year=root_metadata.year,
                )

                if not citation_key:
                    job.send("log", "  → Citation key not found in bibliography.")
                    citation_data = {
                        "paper": _serialize_paper(citing_paper, root_authors=root_metadata.authors),
                        "citations": [{"type": "status", "text": "Citation key not found in .bib"}],
                    }
                    job.send("paper", citation_data)
                    citation_count += 1
                    continue

                job.send("log", f"  → Key: {citation_key}")
                ast = get_ast(tex_content)
                contexts = find_cite_contexts(ast, [citation_key])

                if not contexts:
                    citation_data = {
                        "paper": _serialize_paper(citing_paper, root_authors=root_metadata.authors),
                        "citations": [{"type": "status", "text": "No in-text citations found"}],
                    }
                else:
                    citation_data = {
                        "paper": _serialize_paper(citing_paper, root_authors=root_metadata.authors),
                        "citations": _serialize_contexts(contexts),
                    }

                job.send("paper", citation_data)
                citation_count += 1

            except Exception as e:
                job.send("log", f"  → Error: {e}")
                citation_data = {
                    "paper": _serialize_paper(citing_paper, root_authors=root_metadata.authors),
                    "citations": [{"type": "status", "text": f"Error: {e}"}],
                }
                job.send("paper", citation_data)
                citation_count += 1

        # Cleanup
        if not keep_sources and os.path.exists("data"):
            shutil.rmtree("data")

        job.finish({"total_citations": citation_count, "message": f"Processed {citation_count} citations"})

    except Exception as e:
        job.fail(str(e))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(force=True)
    input_str = data.get("input", "").strip()
    keep_sources = data.get("keep_sources", False)
    source = data.get("source", DEFAULT_SOURCE)
    selected_keywords = data.get("selected_keywords", None)  # NEW: optional keyword filter
    selected_authors = data.get("selected_authors", None)    # NEW: optional author filter

    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    # Validate source
    if source not in ['ads', 'openalex']:
        return jsonify({"error": f"Invalid source: {source}. Must be 'ads' or 'openalex'"}), 400

    job = Job()
    jobs[job.id] = job

    # Pass selected_keywords and selected_authors to _run_job
    t = threading.Thread(target=_run_job, args=(job, input_str, keep_sources, source, selected_keywords, selected_authors), daemon=True)
    t.start()

    return jsonify({"job_id": job.id})


@app.route("/api/get_keywords", methods=["POST"])
def api_get_keywords():
    """
    Fetch all citing papers and extract keywords/topics.
    Returns a list of keywords with their frequencies.
    """
    data = request.get_json(force=True)
    input_str = data.get("input", "").strip()
    source = data.get("source", DEFAULT_SOURCE)

    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    # Validate source
    if source not in ['ads', 'openalex']:
        return jsonify({"error": f"Invalid source: {source}"}), 400

    try:
        # Resolve paper ID
        paper_id = resolve_paper_id(input_str)

        # Get metadata
        root_metadata = get_paper_metadata_multi_source(paper_id, preferred_source=source)

        # Get all citing papers
        citing_papers = get_citations_multi_source(root_metadata, preferred_source=source)

        # Extract keywords
        keywords = _extract_keywords_from_papers(citing_papers)

        # Convert to list for JSON serialization
        keywords_list = [{"keyword": k, "count": v} for k, v in keywords.items()]

        return jsonify({
            "keywords": keywords_list,
            "total_papers": len(citing_papers)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/get_authors", methods=["POST"])
def api_get_authors():
    """
    Fetch citing papers filtered by keywords, extract authors.
    Returns a list of authors with their frequencies.
    """
    data = request.get_json(force=True)
    input_str = data.get("input", "").strip()
    source = data.get("source", DEFAULT_SOURCE)
    selected_keywords = data.get("selected_keywords", [])

    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    if source not in ['ads', 'openalex']:
        return jsonify({"error": f"Invalid source: {source}"}), 400

    try:
        # Resolve paper ID
        paper_id = resolve_paper_id(input_str)

        # Get metadata
        root_metadata = get_paper_metadata_multi_source(paper_id, preferred_source=source)

        # Get all citing papers
        citing_papers = get_citations_multi_source(root_metadata, preferred_source=source)

        # Filter by keywords if specified
        if selected_keywords and len(selected_keywords) > 0:
            filtered_papers = []
            for paper in citing_papers:
                if hasattr(paper, 'topics') and paper.topics:
                    paper_keywords = {t.get('display_name', '') for t in paper.topics}
                    if any(kw in paper_keywords for kw in selected_keywords):
                        filtered_papers.append(paper)
            citing_papers = filtered_papers

        # Extract authors
        authors = _extract_authors_from_papers(citing_papers)

        # Convert to list for JSON serialization
        authors_list = [{"author": a, "count": v} for a, v in authors]

        return jsonify({
            "authors": authors_list,
            "total_papers": len(citing_papers)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/stream/<job_id>")
def api_stream(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    def event_stream():
        while True:
            try:
                msg = job.queue.get(timeout=120)
            except queue.Empty:
                # Keep-alive
                yield ":\n\n"
                continue

            event = msg["event"]
            payload = json.dumps(msg["data"])
            yield f"event: {event}\ndata: {payload}\n\n"

            if event in ("done", "error"):
                break

    return Response(event_stream(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting Citation Constellation web UI on http://localhost:{port}")
    app.run(debug=True, port=port, threaded=True)
