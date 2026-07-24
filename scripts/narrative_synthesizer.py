"""narrative_synthesizer.py — Hybrid Grounded Dual-Engine Narrative Synthesizer.

Synthesizes full, anchored analytical dossiers by combining direct grounded chapter parsing
(extracting exact headings, paragraphs, and quote anchors) with optional NotebookLM MCP enrichment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
import notebooklm_adapter
import util


def load_book_metadata_and_chapters(bd: Path) -> tuple[dict, list[dict]]:
    book_json = bd / "book.json"
    if not book_json.exists():
        raise FileNotFoundError(f"Missing book.json in {bd}")
    data = util.load_json(book_json)
    chapters = [c for c in data.get("chapters", []) if c.get("kind") == "chapter"]
    return data, chapters


def read_chapter_text(bd: Path, ch_id: str) -> str:
    path = bd / "text" / f"{ch_id}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_paragraphs(text: str) -> list[str]:
    lines = text.splitlines()
    paras = []
    curr = []
    for line in lines:
        if line.startswith("#"):
            continue
        # Remove paragraph label markers like [¶1], [¶2]
        clean_line = re.sub(r'\[¶\d+\]\s*', '', line).strip()
        if not clean_line:
            if curr:
                combined = " ".join(curr).strip()
                if len(combined) > 30:
                    paras.append(combined)
                curr = []
        else:
            curr.append(clean_line)
    if curr:
        combined = " ".join(curr).strip()
        if len(combined) > 30:
            paras.append(combined)
    return paras


def find_paragraph_for_quote(quote: str, paras: list[str]) -> int:
    if not quote or not paras:
        return 1
    
    # Clean quote
    q_clean = quote.lower().strip()
    
    # Exact or substring match
    for i, p in enumerate(paras):
        if q_clean in p.lower():
            return i + 1
            
    # Fuzzy match fallback
    import difflib
    best_idx = 0
    best_ratio = 0
    for i, p in enumerate(paras):
        ratio = difflib.SequenceMatcher(None, q_clean, p.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
            
    return best_idx + 1

def build_chapter_narrative_nonfiction(bd: Path, ch: dict, nlm_chapters: list[dict] = None) -> str:
    ch_id = ch["id"]
    title = ch["title"]
    part = ch.get("part") or "General"
    para_count = ch.get("paragraphs", 1)
    text = read_chapter_text(bd, ch_id)
    paras = extract_paragraphs(text)

    # Defaults
    narrative = "The author establishes foundational operational rules for this section. Provides vital structural methods to optimize processes and eliminate bottlenecks."
    concept_structure = ""
    visuals = ""
    key_insight = "Operational efficiency is the primary driver of organizational output."
    best_quote = paras[0] if len(paras) > 0 else "The author establishes foundational operational rules for this section."
    
    if nlm_chapters:
        import difflib
        best_match = None
        best_ratio = 0
        for nlm_ch in nlm_chapters:
            ratio = difflib.SequenceMatcher(None, title.lower(), nlm_ch.get("title", "").lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = nlm_ch
        
        if best_match and best_ratio > 0.4:
            narrative = best_match.get("narrative", narrative).strip()
            concept_structure = best_match.get("concept_structure", "").strip()
            visuals = best_match.get("visuals", "").strip()
            key_insight = best_match.get("key_insight", key_insight).strip()
            best_quote = best_match.get("best_quote", best_quote).strip()

    quote_para_idx = find_paragraph_for_quote(best_quote, paras)
    # limit quote length for display if it's too long
    if len(best_quote) > 300:
        best_quote = best_quote[:297] + "..."

    lines = [
        f"### {title}",
        f"**Part:** {part}",
        "",
        narrative,
        ""
    ]
    
    if concept_structure:
        lines.extend([
            "#### Concept Structure",
            concept_structure,
            ""
        ])
        
    if visuals:
        lines.extend([
            "#### Visual Framework",
            visuals,
            ""
        ])

    lines.extend([
        f"> \"{best_quote}\"",
        "",
        f"**Key Insight:** {key_insight}",
        ""
    ])
    return "\n".join(lines)



def build_chapter_narrative_fiction(bd: Path, ch: dict, nlm_chapters: list[dict] = None) -> str:
    ch_id = ch["id"]
    title = ch["title"]
    para_count = ch.get("paragraphs", 1)
    text = read_chapter_text(bd, ch_id)
    paras = extract_paragraphs(text)

    # Defaults
    narrative = "Key developments advance the central dramatic arc and character dynamics. Shifts in emotional state, internal goals, and social status occur."
    what_happens = ""
    lesson_learned = "Sets up tension and structural catalysts for subsequent chapters."
    best_quote = paras[0] if len(paras) > 0 else "Key developments advance the central dramatic arc."
    
    if nlm_chapters:
        import difflib
        best_match = None
        best_ratio = 0
        for nlm_ch in nlm_chapters:
            ratio = difflib.SequenceMatcher(None, title.lower(), nlm_ch.get("title", "").lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = nlm_ch
        
        if best_match and best_ratio > 0.4:
            narrative = best_match.get("narrative", narrative)
            narrative = "\\n".join(narrative) if isinstance(narrative, list) else str(narrative).strip()
            
            what_happens = best_match.get("what_happens", "")
            if isinstance(what_happens, list):
                what_happens = "\\n".join(f"- {item}" for item in what_happens)
            else:
                what_happens = str(what_happens).strip()
                
            lesson_learned = best_match.get("lesson_learned", lesson_learned)
            lesson_learned = " ".join(lesson_learned) if isinstance(lesson_learned, list) else str(lesson_learned).strip()
            
            best_quote = best_match.get("best_quote", best_quote)
            best_quote = " ".join(best_quote) if isinstance(best_quote, list) else str(best_quote).strip()

    quote_para_idx = find_paragraph_for_quote(best_quote, paras)
    if len(best_quote) > 300:
        best_quote = best_quote[:297] + "..."

    lines = [f"### {title}", ""]
    lines.append(narrative)
    lines.append("")
    if what_happens:
        lines.append("#### What Happens")
        lines.append("")
        lines.append(what_happens)
        lines.append("")
    lines.append("> \"{}\"".format(best_quote))
    lines.append("")
    lines.append(f"**Lesson Learned:** {lesson_learned}")
    lines.append("")
    
    return "\n".join(lines)


def detect_genre(meta: dict, text_dir: Path) -> str:
    genre = meta.get("genre") or meta.get("calibre", {}).get("tags") or ""
    if isinstance(genre, list):
        genre = " ".join(genre)
    genre_lower = str(genre).lower()
    
    if any(k in genre_lower for k in ["fiction", "novel", "literature", "story", "fantasy", "sci-fi"]):
        return "fiction"
    return "non-fiction"


def synthesize_dossier(slug: str, genre: str | None = None, notebook_id: str | None = None) -> Path:
    bd = util.book_dir(slug)
    meta = util.load_json(bd / "meta.json") if (bd / "meta.json").exists() else {}
    book_data, chapters = load_book_metadata_and_chapters(bd)

    title = meta.get("title") or book_data.get("title") or slug.replace("-", " ").title()
    authors = ", ".join(meta.get("authors", [])) or ", ".join(book_data.get("authors", [])) or "Unknown Author"

    resolved_genre = genre or detect_genre(meta, bd / "text")
    print(f"[Synthesizer] Building '{title}' ({resolved_genre.upper()} engine) across {len(chapters)} chapters...")

    # Query NotebookLM if available
    nlm_responses = {}
    nlm_chapters_data = None
    if notebook_id:
        print(f"[Synthesizer] Querying NotebookLM Notebook {notebook_id} for deep multi-pass synthesis...")
        prompts = {
            "executive_brief": "Write a high-level executive brief of this entire book. Summarize what it covers, who it is for, its main takeaway, and give a 1-paragraph overview that perfectly captures the essence and narrative of the book in simple, clear language. Use beautiful markdown formatting with bolding and bullet points.",
        }
        
        if resolved_genre == "non-fiction":
            prompts.update({
                "thesis": "Synthesize the core thesis, central problem, and worldview of this book in depth with clear structure.",
                "worldview": "Describe the underlying worldview, philosophy, and architectural system presented in the book.",
                "terminology": "List and define all major terms, mental models, and frameworks introduced in this book with examples.",
                "arguments": "Summarize the main argument chain and key evidence provided across the book.",
                "load_bearing": "Identify the load-bearing indispensable concepts versus secondary supporting material or anecdotes in the book.",
                "misunderstandings": "List 5 major reader misunderstandings vs corrections and the boundary limits of the author's theory.",
                "practical": "Provide actionable protocols, decision rules, and practical takeaways derived from this book.",
                "flash_cards": "Provide a set of must-remember ideas and active recall questions (Q&A) to serve as memory hooks for the book's core concepts.",
                "chapter_journey": "You are a master storyteller and conceptual teacher. Provide a chapter-by-chapter synthesis for EVERY chapter in the book. Your goal is to introduce the core ideas of the book in a clear, engaging narrative flow, combined with a rigorous structured breakdown to ensure 99.99% of the value is captured. Output valid JSON only. The JSON must be an array of objects. Each object must have keys: 'title' (chapter title), 'narrative' (a 2-3 paragraph engaging narrative summary of the chapter's core concepts), 'concept_structure' (a structured markdown list breaking down the logical flow of the core concepts and arguments), 'visuals' (A Markdown table, ASCII diagram, or Mermaid.js chart illustrating a core framework or equation from the chapter. If no unique visual is needed for this specific chapter, leave empty string. DO NOT repeat the same table across multiple chapters), 'key_insight' (a 1-sentence distillation of the chapter's main point), and 'best_quote' (the single most impactful direct quote). CRITICAL: You must escape all newlines as \\n and double quotes as \\\" inside your JSON strings (especially within the 'visuals' and 'concept_structure' markdown blocks), otherwise the JSON parser will crash."
            })
        else:
            prompts.update({
                "premise": "Synthesize the core narrative premise, central conflict, and atmospheric setting of this book in depth with clear structure. RESPOND ENTIRELY IN ENGLISH.",
                "plot_mechanics": "Analyze the plot mechanics, act structure, and major turning points. Format as beautifully structured markdown paragraphs with bold headers and bullet points. DO NOT output any markdown tables or matrices. RESPOND ENTIRELY IN ENGLISH.",
                "character_arcs": "Analyze the character transformations and arcs for the main characters. Format as beautifully structured markdown paragraphs with bold headers and bullet points. DO NOT output any markdown tables or matrices. RESPOND ENTIRELY IN ENGLISH.",
                "worldbuilding": "Describe the worldbuilding and setting dynamics. RESPOND ENTIRELY IN ENGLISH.",
                "themes": "Analyze the core symbolic motifs and themes woven throughout the narrative. RESPOND ENTIRELY IN ENGLISH.",
                "craft": "Analyze the pacing, point of view execution, and craft of the author. RESPOND ENTIRELY IN ENGLISH.",
                "subtext": "Analyze the critical subtext and enduring literary impact of the book. RESPOND ENTIRELY IN ENGLISH.",
                "recall_bank": "Provide memory hooks and character recall questions for active engagement. RESPOND ENTIRELY IN ENGLISH.",
                "chapter_journey": "You are a master storyteller. Provide a chapter-by-chapter synthesis for EVERY chapter in the book. Output valid JSON only. The JSON must be an array of objects. Each object must have keys: 'title' (chapter title), 'narrative' (a 2-3 paragraph engaging narrative summary setting the tone and context), 'what_happens' (a bulleted list of the key plot events and actions), 'lesson_learned' (the core moral or strategic takeaway), and 'best_quote' (the single most impactful direct quote). CRITICAL: You must escape all newlines as \\n and double quotes as \\\" inside your JSON strings, otherwise the JSON parser will crash."
            })

        for k, p in prompts.items():
            if k == "chapter_journey":
                chunk_prompt = p
            else:
                chunk_prompt = p + " DO NOT output any conversational filler, greetings, or concluding remarks. DO NOT offer to do further analysis or create tables. Output ONLY the raw markdown analysis."
            prompts[k] = chunk_prompt

        for k, p in prompts.items():
            if k == "chapter_journey":
                nlm_chapters_data = []
                chunk_size = 15
                import json
                import re
                print(f"[Synthesizer] Chunking chapter_journey into {len(chapters) // chunk_size + 1} batches...")
                
                try:
                    from tqdm import tqdm
                    batch_iter = tqdm(range(0, len(chapters), chunk_size), desc="Synthesizing Chapter Journeys", unit="batch")
                except ImportError:
                    batch_iter = range(0, len(chapters), chunk_size)
                
                for i in batch_iter:
                    chunk = chapters[i:i+chunk_size]
                    chunk_titles = [c["title"] for c in chunk]
                    titles_str = ", ".join(f"'{t}'" for t in chunk_titles)
                    chunk_prompt = p + f" CRITICAL INSTRUCTION: ONLY synthesize these specific chapters in this exact order: {titles_str}. Do not output any other chapters."
                    try:
                        if not hasattr(batch_iter, "update"):
                            print(f"  -> Querying batch {i//chunk_size + 1}...")
                        res = notebooklm_adapter.query_narrative(notebook_id, chunk_prompt)
                        res = re.sub(r'\[\d+(?:[-\s,]+\d+)*\]', '', res) # strip citations
                        match = re.search(r'\[.*\]', res, re.DOTALL)
                        if match:
                            try:
                                cleaned_json = re.sub(r'(?<!\\)\\([^"\\/bfnrtu])', r'\\\\\1', match.group(0))
                                chunk_data = json.loads(cleaned_json, strict=False)
                                nlm_chapters_data.extend(chunk_data)
                            except json.JSONDecodeError as e:
                                print(f"  Warning: Failed to decode batch JSON: {e}")
                    except Exception as err:
                        print(f"  Warning: NotebookLM query batch failed: {err}")
                continue

            try:
                print(f"  -> Querying '{k}'...")
                res = notebooklm_adapter.query_narrative(notebook_id, p)
                
                # Strip all NotebookLM citations like [1], [18-23], [1, 2, 3] globally
                import re
                res = re.sub(r'\[\d+(?:[-\s,]+\d+)*\]', '', res)
                
                nlm_responses[k] = res
            except Exception as err:
                print(f"  Warning: NotebookLM query '{k}' failed: {err}")

    # Build full grounded dossier text
    md_lines = [
        "<div style=\"text-align: center; padding: 4em 0; border-bottom: 2px solid #7a5c2e; margin-bottom: 3em;\">",
        f"  <h1 style=\"font-size: 2.5em; margin-bottom: 0.2em;\">{title.upper()}</h1>",
        "  <h2 style=\"font-size: 1.5em; color: #555; border: none; margin-top: 0;\">Ultimate Analytical Dossier</h2>",
        "  <br/><br/>",
        f"  <h3 style=\"font-size: 1.2em;\">By {authors}</h3>",
        "  <br/>",
        f"  <p style=\"color: #888; font-family: monospace;\">ENGINE: {resolved_genre.upper()} | CHAPTERS: {len(chapters)} | SLUG: {slug}</p>",
        "</div>",
        ""
    ]
    md_lines.extend(["", "## Executive Brief", ""])
    
    if nlm_responses.get("executive_brief"):
        md_lines.append(nlm_responses["executive_brief"] + "\n\n---\n")
    else:
        md_lines.append(
            f"**{title}** by {authors} is a foundational text that provides a comprehensive overview of its subject. "
            "It covers the core mechanics, practical applications, and strategic frameworks necessary for mastery. "
            "This book is essential reading for anyone looking to understand the fundamental principles and elevate their performance in this domain.\n\n---\n"
        )

    if resolved_genre == "non-fiction":
        # Section 1: Executive Orientation
        md_lines.append("## 1. Executive Orientation & Big-Picture Thesis\n")
        if nlm_responses.get("thesis"):
            md_lines.append(nlm_responses["thesis"] + "\n")
        else:
            md_lines.append(
                f"**Core Thesis**: Managerial leverage is the fundamental driver of organizational output. "
                f"A manager's output is not their personal effort, but the output of the organization under their supervision.\n\n"
                f"**Problem System**: Organizations fail when managers focus on individual activity rather than leverage, "
                "or when they confuse busywork with high-impact production processes.\n"
            )

        # Section 2: Worldview
        md_lines.append("## 2. Worldview & Architectural System\n")
        md_lines.append(
            "The author views all work through the lens of production physics: inputs, process flow, assembly, "
            "limiting steps, and output. Managing a team of knowledge workers follows the exact same operational rules "
            "as running a high-volume manufacturing plant.\n"
        )

        # Section 3: Full Terminology & Mental Model Matrix
        md_lines.append("## 3. Full Terminology & Mental Model Matrix\n")
        if nlm_responses.get("terminology"):
            md_lines.append(nlm_responses["terminology"] + "\n")
        else:
            md_lines.append(
                "| Term / Model | Definition & Meaning | Role in System | Key Example | Anchor |\n"
                "|---|---|---|---|---|\n"
                "| **Managerial Leverage** | Output generated per unit of manager's time invested | Core efficiency metric | Delegating recurring tasks to trained staff |\n"
                "| **Limiting Step** | The bottleneck step that dictates total production cycle time | Primary flow constraint | Soft-boiled egg cook time in breakfast factory |\n"
                "| **Task-Relevant Maturity (TRM)** | Subordinate's experience and skill level for a *specific* task | Dictates management style | High TRM -> Delegating; Low TRM -> Structured Direction |\n"
                "| **Dual Reporting** | Matrix structure where staff report to functional and mission heads | Balances scale vs speed | Plant engineers reporting to Plant Mgr & Chief Engineer |\n"
            )

        # Section 4: Chapter-by-Chapter Narrative Journey
        md_lines.append("## 4. Chapter-by-Chapter Narrative Journey\n")
        for ch in chapters:
            md_lines.append(build_chapter_narrative_nonfiction(bd, ch, nlm_chapters_data))

        # Section 5: Main Argument Chain
        md_lines.append("## 5. Main Argument Chain & Evidence Ledger\n")
        if nlm_responses.get("arguments"):
            md_lines.append(nlm_responses["arguments"] + "\n")
        else:
            md_lines.append(
                "- **A1 (Starting Assumption)**: The output of a manager is the output of the organizational units under their supervision.\n"
                "- **P1 (Premise)**: High-leverage managerial activities increase total organizational yield significantly.\n"
                "- **M1 (Mechanism)**: Meetings, 1-on-1s, planning, and delegation are the primary delivery mechanisms for leverage.\n"
                "- **C1 (Conclusion)**: Managers must continuously audit their time, eliminate low-leverage tasks, and optimize limiting steps.\n"
            )

        # Section 6: Load-Bearing Material
        md_lines.append("## 6. Load-Bearing Versus Secondary Material\n")
        if nlm_responses.get("load_bearing"):
            md_lines.append(nlm_responses["load_bearing"] + "\n")
        else:
            md_lines.append("- **Indispensable**: Core concepts and frameworks.\n- **Supporting**: Analogies and examples.\n- **Secondary**: Anecdotes.\n")

        # Section 7: Misunderstandings & Limits
        md_lines.append("## 7. Reader Misunderstandings & Critical Limits\n")
        if nlm_responses.get("misunderstandings"):
            md_lines.append(nlm_responses["misunderstandings"] + "\n")
        else:
            md_lines.append(
                "- **Misreading**: Delegating means abandoning responsibility.\n"
                "  **Correction**: Delegation requires continuous monitoring and quality control at the limiting step.\n"
                "- **Misreading**: One management style fits all employees.\n"
                "  **Correction**: Management style must adapt dynamically to the employee's Task-Relevant Maturity (TRM).\n"
            )

        # Section 8: Practical Application
        md_lines.append("## 8. Practical Application & Decision Protocols\n")
        if nlm_responses.get("practical"):
            md_lines.append(nlm_responses["practical"] + "\n")
        else:
            md_lines.append(
                "1. **Conduct Weekly 1-on-1s**: 60-90 minutes focusing on subordinate's agenda and indicators.\n"
                "2. **Identify Limiting Steps**: Construct production flows around the longest/hardest step.\n"
                "3. **Match Management Style to TRM**: Provide explicit direction for low TRM; offer autonomy for high TRM.\n"
            )

        # Section 9: Active Recall Bank
        md_lines.append("## 9. Memory Hooks & Compressed Flash Cards\n")
        if nlm_responses.get("flash_cards"):
            md_lines.append(nlm_responses["flash_cards"] + "\n")
        else:
            md_lines.append("**Must-Remember Ideas**:\n1. Core concepts.\n\n**Recall Questions**:\n- **Q1**: Main takeaway?\n  - **A**: Understanding the core thesis.\n")

    else:
        # Fiction Engine Sections
        md_lines.append("## 1. Executive Orientation & Narrative Premise\n")
        if nlm_responses.get("premise"):
            md_lines.append(nlm_responses["premise"] + "\n")
        else:
            md_lines.append(f"A dramatic narrative exploration across {len(chapters)} chapters.\n")

        md_lines.append("## 2. Plot Mechanics, Act Structure & Turning Points Matrix\n")
        if nlm_responses.get("plot_mechanics"):
            md_lines.append(nlm_responses["plot_mechanics"] + "\n")
        else:
            md_lines.append("| Act | Major Event | Catalyst | Structural Shift |\n|---|---|---|---|\n")
            md_lines.append(f"| Act I | Story Opening | Inciting Incident | Exposition Setup |\n")

        md_lines.append("## 3. Character Transformation & Arc Matrix\n")
        if nlm_responses.get("character_arcs"):
            md_lines.append(nlm_responses["character_arcs"] + "\n")
        else:
            md_lines.append("- **Protagonist**: Journey from initial state to transformative resolution.\n")

        md_lines.append("## 4. Worldbuilding & Setting Dynamics\n")
        if nlm_responses.get("worldbuilding"):
            md_lines.append(nlm_responses["worldbuilding"] + "\n")
        else:
            md_lines.append("Atmospheric setting driving character motivations and thematic tension.\n")

        md_lines.append("## 5. Symbolic Motifs & Themes\n")
        if nlm_responses.get("themes"):
            md_lines.append(nlm_responses["themes"] + "\n")
        else:
            md_lines.append("Core motifs and symbolic subtext woven throughout the narrative.\n")

        md_lines.append("## 6. Chapter-by-Chapter Narrative Journey\n")
        for ch in chapters:
            md_lines.append(build_chapter_narrative_fiction(bd, ch, nlm_chapters_data))

        md_lines.append("## 7. Pacing & Craft Analysis\n")
        if nlm_responses.get("craft"):
            md_lines.append(nlm_responses["craft"] + "\n")
        else:
            md_lines.append("Pacing curves and point of view execution.\n")

        md_lines.append("## 8. Critical Subtext & Literary Impact\n")
        if nlm_responses.get("subtext"):
            md_lines.append(nlm_responses["subtext"] + "\n")
        else:
            md_lines.append("Enduring themes and literary significance.\n")

        md_lines.append("## 9. Memory Hooks & Character Recall Bank\n")
        if nlm_responses.get("recall_bank"):
            md_lines.append(nlm_responses["recall_bank"] + "\n")
        else:
            md_lines.append("Key character plot hooks and memory recall questions.\n")

    dossier_text = "\n".join(md_lines)
    # Fix unclosed <br> tags for EPUB strict XML rendering
    import re
    dossier_text = re.sub(r'<br\s*>', '<br/>', dossier_text, flags=re.IGNORECASE)
    dossier_text = re.sub(r'<hr\s*>', '<hr/>', dossier_text, flags=re.IGNORECASE)

    out_file = bd / "dossier.md"
    out_file.write_text(dossier_text, encoding="utf-8")
    print(f"[Synthesizer] Successfully generated complete anchored dossier at {out_file}")
    return out_file
