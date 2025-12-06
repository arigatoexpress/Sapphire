# Contributing to Agent Symphony

Thank you for your interest in contributing to Agent Symphony! This document provides guidelines and instructions for contributing.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [Branching Strategy](#branching-strategy)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)

---

## 📜 Code of Conduct

By participating in this project, you agree to maintain a professional and respectful environment.

---

## 🛠️ Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker
- Google Cloud SDK

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/arigatoexpress/AsterAI.git
cd AsterAI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp env.example .env
# Edit .env with your credentials
```

### Frontend Setup

```bash
cd trading-dashboard
npm install
cp .env.example .env.local
npm run dev
```

### Verify Setup

```bash
# Run tests
pytest tests/ -v

# Lint code
ruff check .

# Type check
mypy cloud_trader/
```

---

## 🌿 Branching Strategy

We follow **GitHub Flow**:

```
main (production)
  └── feature/your-feature
  └── fix/bug-description
  └── refactor/component-name
```

### Branch Naming

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feature/` | New functionality | `feature/grok-agent` |
| `fix/` | Bug fixes | `fix/telegram-timeout` |
| `refactor/` | Code improvements | `refactor/trading-loop` |
| `docs/` | Documentation | `docs/architecture` |
| `chore/` | Maintenance | `chore/update-deps` |

---

## ✍️ Commit Guidelines

We use **Conventional Commits**:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `style` | Formatting (no logic change) |
| `refactor` | Code restructuring |
| `test` | Adding tests |
| `chore` | Maintenance tasks |

### Examples

```bash
feat(trading): add new entry logic for agents
fix(telegram): resolve silent notification failures
docs(readme): add architecture diagrams
refactor(client): extract position manager
```

---

## 🔀 Pull Request Process

1. **Create a feature branch** from `main`
2. **Make your changes** with clear commits
3. **Run tests** and linting locally
4. **Push** and create a Pull Request
5. **Fill out the PR template**
6. **Request review** from maintainers
7. **Address feedback** if any
8. **Merge** once approved

### PR Checklist

- [ ] Tests pass locally
- [ ] Code is linted and type-checked
- [ ] Documentation updated if needed
- [ ] No secrets or credentials in code
- [ ] Meaningful commit messages

---

## 🎨 Code Style

### Python

We use **Ruff** for linting and formatting:

```bash
ruff check .
ruff format .
```

Key conventions:
- Line length: 100 characters
- Use type hints for all functions
- Docstrings for public functions
- Async/await for I/O operations

### TypeScript

We use **ESLint** and **Prettier**:

```bash
cd trading-dashboard
npm run lint
npm run format
```

---

## 🧪 Testing

### Python Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=cloud_trader

# Run specific test file
pytest tests/test_trading_service.py -v
```

### Frontend Tests

```bash
cd trading-dashboard
npm test
```

---

## 📁 File Organization

When adding new features:

```
cloud_trader/
├── feature_name.py       # Main implementation
├── feature_name_test.py  # Tests (or in tests/)
└── __init__.py           # Export new modules
```

---

## 🔐 Security

- Never commit API keys or secrets
- Use `.env` files for local development
- All secrets in Google Secret Manager for production
- Run security scans before PRs

---

## 💬 Getting Help

- Check existing [issues](https://github.com/arigatoexpress/AsterAI/issues)
- Read the [documentation](docs/)
- Ask in project discussions

---

<div align="center">
<sub>Thank you for contributing! 🎉</sub>
</div>
