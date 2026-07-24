# Changelog

## [v1.0.0] - The Fiction Engine & API Resiliency Update

This major release introduces full support for synthesizing fiction books and significantly improves the robustness of the core extraction engine when dealing with massive texts.

### 🚀 New Features
- **Fiction Analytical Engine**: A brand new dedicated synthesis pipeline for fiction literature. Automatically extracts and structures Plot Mechanics, Worldbuilding Dynamics, Character Arcs, and Thematic Subtext.
- **Batch Processing via NotebookLM Adapter**: Completely bypasses previous API context limits and read timeouts by processing chapter journeys in automated chunks. Massive books (e.g., 100+ chapters) can now be synthesized seamlessly.
- **Automated Indexing**: The `booker.py index` command now injects and updates a live library catalog directly into the `README.md`.

### 🛠️ Fixes & Improvements
- **Strict Formatting Guards**: Added robust regex and prompt constraints to completely ban AI conversational filler, unsolicited tables, and language drift hallucinations.
- **EPUB Rendering Fixes**: Repaired issues with unclosed HTML tags and inline markdown lists that previously caused Pandoc EPUB rendering to crash.
- **Documentation Overhaul**: Redesigned the README with a professional, badge-heavy layout and clearer structural sections. 
