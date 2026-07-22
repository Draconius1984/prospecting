#!/usr/bin/env python3
"""
Local browser UI for OT Prospector.

Run:
    python webapp/app.py
    # then open http://localhost:5000

It reuses prospector/pipeline.py, so results are identical to the CLI. Jobs run
in background threads; the page polls for live logs + results.

This binds to 127.0.0.1 (your machine only) by design — it is a local tool, not
a public server. Read docs/COMPLIANCE.md before contacting anyone.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import threading
import uuid
from typing import Dict, List

# Make the prospector package importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from flask import Flask, Response, jsonify, render_template, request

from prospector import __version__, enrich, search
from prospector.models import CSV_FIELDS, Prospect
from prospector.pipeline import (
    crawl_sites,
    dedupe,
    discover_urls,
    urls_from_text,
    validate_prospects,
    write_prospects,
)
from prospector.sources import CURATED_SOURCES, QLD_REGIONS

app = Flask(__name__)

# In-memory job store. Fine for a single-user local tool.
JOBS: Dict[str, dict] = {}
LOCK = threading.Lock()
MAX_LOG_LINES = 500


# --------------------------------------------------------------------------
# Job helpers
# --------------------------------------------------------------------------
def _new_job(mode: str) -> str:
    job_id = uuid.uuid4().hex[:8]
    with LOCK:
        JOBS[job_id] = {"status": "running", "mode": mode, "logs": [], "prospects": [], "error": ""}
    return job_id


def _log(job_id: str, msg: str) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["logs"].append(msg)
        if len(job["logs"]) > MAX_LOG_LINES:
            job["logs"] = job["logs"][-MAX_LOG_LINES:]


def _emit(job_id: str, p: Prospect) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if job:
            job["prospects"].append(p)


def _finish(job_id: str, deduped: List[Prospect], do_validate: bool) -> None:
    if do_validate:
        _log(job_id, "Validating emails (syntax + MX record)...")
        validate_prospects(deduped, on_log=lambda m: _log(job_id, m))
    with LOCK:
        job = JOBS.get(job_id)
        if job:
            job["prospects"] = deduped
            job["status"] = "done"
    got = sum(1 for p in deduped if p.email)
    _log(job_id, f"Finished: {len(deduped)} unique record(s), {got} with an email.")


def _fail(job_id: str, exc: Exception) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if job:
            job["status"] = "error"
            job["error"] = str(exc)
    _log(job_id, f"ERROR: {exc}")


# --------------------------------------------------------------------------
# Workers (run in background threads)
# --------------------------------------------------------------------------
def _worker_crawl(job_id, urls, delay, max_pages, do_validate):
    try:
        _log(job_id, f"Crawling {len(urls)} candidate site(s)...")
        found = crawl_sites(
            urls, delay=delay, max_pages=max_pages,
            on_log=lambda m: _log(job_id, m),
            on_result=lambda p: _emit(job_id, p),
        )
        _finish(job_id, dedupe(found), do_validate)
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)


def _worker_discover(job_id, regions, per_query, delay, max_pages, do_validate):
    try:
        urls = discover_urls(regions=regions, per_query=per_query, on_log=lambda m: _log(job_id, m))
        _log(job_id, f"{len(urls)} candidate URL(s) discovered; crawling clinic sites...")
        found = crawl_sites(
            urls, delay=delay, max_pages=max_pages,
            on_log=lambda m: _log(job_id, m),
            on_result=lambda p: _emit(job_id, p),
        )
        _finish(job_id, dedupe(found), do_validate)
    except Exception as exc:  # noqa: BLE001
        _fail(job_id, exc)


def _spawn(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", version=__version__)


@app.route("/api/config")
def api_config():
    return jsonify({
        "version": __version__,
        "search_provider": search.active_provider(),
        "hunter_enabled": enrich.enabled(),
        "regions": [r["region"] for r in QLD_REGIONS],
        "sources": CURATED_SOURCES,
    })


@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    data = request.get_json(force=True) or {}
    urls = [p.website for p in urls_from_text(data.get("urls", ""))]
    if not urls:
        return jsonify({"error": "Paste at least one website URL (one per line)."}), 400
    delay = float(data.get("delay", 2.0))
    max_pages = int(data.get("max_pages", 5))
    do_validate = bool(data.get("validate", True))
    job_id = _new_job("crawl")
    _spawn(_worker_crawl, job_id, urls, delay, max_pages, do_validate)
    return jsonify({"job_id": job_id})


@app.route("/api/discover", methods=["POST"])
def api_discover():
    if search.active_provider() == "none":
        return jsonify({"error": "No search API key configured. Add SERPAPI_API_KEY (or Google/Bing) to .env, or use Crawl mode."}), 400
    data = request.get_json(force=True) or {}
    wanted = {r.strip().lower() for r in data.get("regions", [])}
    regions = [r for r in QLD_REGIONS if r["region"].lower() in wanted] or QLD_REGIONS
    per_query = int(data.get("per_query", 10))
    delay = float(data.get("delay", 2.0))
    max_pages = int(data.get("max_pages", 5))
    do_validate = bool(data.get("validate", True))
    job_id = _new_job("discover")
    _spawn(_worker_discover, job_id, regions, per_query, delay, max_pages, do_validate)
    return jsonify({"job_id": job_id})


@app.route("/api/jobs/<job_id>")
def api_job(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        prospects = [p.to_row() for p in job["prospects"]]
        return jsonify({
            "status": job["status"],
            "mode": job["mode"],
            "logs": job["logs"],
            "error": job["error"],
            "count": len(prospects),
            "with_email": sum(1 for r in prospects if r.get("email")),
            "flagged": sum(1 for r in prospects if r.get("status") == "flagged"),
            "prospects": prospects,
        })


@app.route("/api/jobs/<job_id>/download")
def api_download(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        rows = [p.to_row() for p in job["prospects"]]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prospects_{job_id}.csv"},
    )


@app.route("/api/jobs/<job_id>/save", methods=["POST"])
def api_save(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "unknown job"}), 404
        prospects = list(job["prospects"])
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prospects.csv"
    )
    n = write_prospects(out, prospects)
    return jsonify({"saved": n, "path": out})


if __name__ == "__main__":
    import webbrowser

    port = int(os.getenv("PORT", "5000"))
    url = f"http://localhost:{port}"
    print("=" * 56)
    print(f"  OT Prospector web UI is starting...")
    print(f"  Open this in your browser:  {url}")
    print(f"  (Press Ctrl+C in this window to stop the server.)")
    print("=" * 56)
    # Auto-open the browser shortly after the server is up. Set NO_BROWSER=1 to skip.
    if os.getenv("NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
