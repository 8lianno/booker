# Contributing to Booker

First off, thank you for considering contributing to Booker! It's people like you that make open-source projects thrive.

## How Can I Contribute?

### 1. Reporting Bugs
If you find a bug, please submit an issue containing:
* A clear and descriptive title.
* Steps to reproduce the issue.
* The exact error message (if any).
* Details about your environment (Python version, OS, etc.).

*Note: If you discover a security vulnerability, please refer to our [SECURITY.md](SECURITY.md) instead of creating a public issue.*

### 2. Suggesting Enhancements
We welcome ideas for new features or improvements to the analytical engines. When submitting an enhancement idea, please provide:
* The goal of the new feature.
* A suggested implementation path (if you have one).
* Examples of how it would improve the generated dossiers.

### 3. Submitting Pull Requests
If you want to contribute code (bug fixes, new features, or prompt tweaks):
1. **Fork the repository** and create your branch from `main`.
2. **Install dependencies** (ensure you have `pandoc` and `weasyprint` installed locally).
3. **Make your changes**. If you are adding a new synthesis engine or changing the core adapter, please add tests.
4. **Follow `AGENTS.md`**: Since this project relies heavily on autonomous agents, ensure your code remains readable and easily parsed by LLMs.
5. **Issue a Pull Request** with a clear title and description of the changes.

## Development Setup
```bash
# Clone the repository
git clone https://github.com/8lianno/booker.git
cd booker

# Install dependencies (ensure Pandoc is installed on your OS)
pip install -r requirements.txt
```

Thank you for helping us extract the essence of literature!
