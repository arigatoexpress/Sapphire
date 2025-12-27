# Contributing to Sapphire AI

Thank you for your interest in contributing to Sapphire! This document provides guidelines and instructions for maintaining our **Pristine Codebase Standards**.

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [The "Pristine" Standard](#the-pristine-standard)
- [Branching Strategy](#branching-strategy)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)

---

## 🛠️ Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & GCloud CLI

### Setup
```bash
# Clone the repository
git clone https://github.com/arigatoexpress/AsterAI.git
cd AsterAI

# Frontend setup
cd trading-dashboard && npm install && cd ..

# Backend setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 💎 The "Pristine" Standard

We maintain a high bar for repository cleanliness. Contributions must adhere to:

1.  **Strict Modularization**: New internal tools or non-runtime code must go to `internal/`.
2.  **Zero-Stray Policy**: No temporary log files, JSON reports, or stray scripts in the root.
3.  **No Direct Imports from Root**: Core logic lives in `cloud_trader/`.
4.  **Standardized Entry**: Use `start.py` for all local and production execution.

---

## 🌿 Branching & Commits

We use **GitHub Flow** and **Conventional Commits**:

- `feat(agents):` New signal logic
- `fix(router):` Repair execution flow
- `docs(pristine):` Documentation updates
- `refactor(core):` Restructuring modules

---

## 🔀 Pull Request Process

1.  **Branch** from `main`.
2.  **Verify**: Run `python3 start.py --verify-only`.
3.  **Template**: Fill out the detailed PR template.
4.  **Review**: At least one maintainer approval required.

---
## 🔐 Security
- **Never commit secrets**.
- All production keys are managed via GCP Secret Manager.
- Use `Settings` in `config.py` for all environment variables.

---
<div align="center">
<sub>Built with Precision. Trading with Intelligence. 🎉</sub>
</div>
