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
from core.fetcher import get_paper_metadata, get_citations
from core.downloader import download_source, extract_source, find_main_tex
from core.parser import get_ast, find_citations as find_cite_contexts, find_key_for_paper, resolve_latex_inclusions

app = Flask(__name__)

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


def _serialize_paper(paper):
    return {
        "title": paper.title,
        "authors": paper.authors[:5] if paper.authors else [],
        "authors_truncated": len(paper.authors) > 5 if paper.authors else False,
        "year": paper.year,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "bibcode": paper.bibcode,
    }


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
def _run_job(job, input_str, keep_sources):
    try:
        # 1. Resolve input
        job.send("log", f"Resolving input: {input_str}")
        paper_id = resolve_paper_id(input_str)
        job.send("log", f"Resolved to: {paper_id}")

        # 2. Metadata
        job.send("log", "Fetching metadata from ADS…")
        root_metadata = get_paper_metadata(paper_id)
        job.send("log", f"Target paper: {root_metadata.title}")
        job.send("root", _serialize_paper(root_metadata))

        if not root_metadata.bibcode:
            job.send("log", "⚠ No bibcode — citation queries may fail.")

        # 3. Citations
        job.send("log", "Fetching citing papers (limit 25)…")
        citing_papers = get_citations(root_metadata.bibcode)
        citing_papers = citing_papers[:25]
        job.send("log", f"Found {len(citing_papers)} citing papers.")
        job.send("total", len(citing_papers))

        results = []

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
                results.append({
                    "paper": _serialize_paper(citing_paper),
                    "citations": [{"type": "status", "text": "Source not available"}],
                })
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
                    results.append({
                        "paper": _serialize_paper(citing_paper),
                        "citations": [{"type": "status", "text": "Citation key not found in .bib"}],
                    })
                    continue

                job.send("log", f"  → Key: {citation_key}")
                ast = get_ast(tex_content)
                contexts = find_cite_contexts(ast, [citation_key])

                if not contexts:
                    results.append({
                        "paper": _serialize_paper(citing_paper),
                        "citations": [{"type": "status", "text": "No in-text citations found"}],
                    })
                else:
                    results.append({
                        "paper": _serialize_paper(citing_paper),
                        "citations": _serialize_contexts(contexts),
                    })

            except Exception as e:
                job.send("log", f"  → Error: {e}")
                results.append({
                    "paper": _serialize_paper(citing_paper),
                    "citations": [{"type": "status", "text": f"Error: {e}"}],
                })

        # Cleanup
        if not keep_sources and os.path.exists("data"):
            shutil.rmtree("data")

        job.finish({"root": _serialize_paper(root_metadata), "citations": results})

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

    if not input_str:
        return jsonify({"error": "No input provided"}), 400

    job = Job()
    jobs[job.id] = job

    t = threading.Thread(target=_run_job, args=(job, input_str, keep_sources), daemon=True)
    t.start()

    return jsonify({"job_id": job.id})


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
