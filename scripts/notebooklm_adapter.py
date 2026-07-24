"""notebooklm_adapter.py — Integration adapter between Booker and NotebookLM MCP/Tools.

Provides high-level helpers to create notebooks for books, upload chapter text files as sources,
run grounded multi-pass narrative queries, and generate audio podcast overviews.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add notebooklm-mcp-cli site-packages to sys.path if not present
NLM_SITE_PACKAGES = "/Users/ali/.local/share/uv/tools/notebooklm-mcp-cli/lib/python3.11/site-packages"
if NLM_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, NLM_SITE_PACKAGES)

try:
    from notebooklm_tools.core.client import NotebookLMClient
except ImportError:
    NotebookLMClient = None


def get_client() -> NotebookLMClient:
    if NotebookLMClient is None:
        raise RuntimeError("notebooklm_tools is not installed in %s" % NLM_SITE_PACKAGES)
    from notebooklm_tools.core.auth import get_auth_manager
    auth = get_auth_manager()
    if not auth.profile_exists():
        raise RuntimeError("No NotebookLM auth profile found. Run `notebooklm-mcp-cli auth login` first.")
    cookies = auth.get_raw_cookies()
    return NotebookLMClient(cookies=cookies)


def setup_book_notebook(slug: str, title: str, text_dir: Path) -> dict:
    """Create a NotebookLM notebook for a book and add all chapter files as sources."""
    client = get_client()
    print(f"[NotebookLM] Creating notebook for '{title}' (slug: {slug})...")
    nb = client.create_notebook(title=f"Booker Dossier: {title}")
    
    if hasattr(nb, "id"):
        notebook_id = nb.id
    elif hasattr(nb, "notebook_id"):
        notebook_id = nb.notebook_id
    elif isinstance(nb, dict):
        notebook_id = nb.get("id") or nb.get("notebook_id") or nb.get("notebook", {}).get("id")
    else:
        notebook_id = None
        
    if not notebook_id:
        raise RuntimeError(f"Failed to extract notebook_id from response: {nb}")

    print(f"[NotebookLM] Created notebook {notebook_id}. Uploading chapter sources...")
    chapter_files = sorted(text_dir.glob("*.md")) + sorted(text_dir.glob("*.txt"))
    added_sources = []

    for fpath in chapter_files:
        print(f"  -> Uploading {fpath.name}...")
        try:
            res = client.add_file(notebook_id, str(fpath))
            added_sources.append({"file": fpath.name, "result": res})
        except Exception as err:
            print(f"     Warning: Failed to upload {fpath.name}: {err}")

    return {
        "slug": slug,
        "title": title,
        "notebook_id": notebook_id,
        "url": f"https://notebooklm.google.com/notebook/{notebook_id}",
        "sources_count": len(added_sources),
        "sources": added_sources,
    }


def query_narrative(notebook_id: str, prompt_text: str) -> str:
    """Execute a grounded multi-pass query against the NotebookLM notebook."""
    client = get_client()
    res = client.query(notebook_id, prompt_text)
    if isinstance(res, dict):
        return res.get("answer") or res.get("response") or res.get("text") or str(res)
    return str(res)


def create_audio_podcast(notebook_id: str) -> dict:
    """Trigger creation of NotebookLM Deep Dive Audio Overview."""
    client = get_client()
    print(f"[NotebookLM] Requesting Deep Dive Audio Overview for notebook {notebook_id}...")
    try:
        res = client.create_audio_overview(notebook_id)
        return {"status": "success", "response": res}
    except Exception as err:
        return {"status": "error", "message": str(err)}
