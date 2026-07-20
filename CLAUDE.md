# CLAUDE.md

# EcoTrace India — Repository Instructions for Claude Code

Version: 1.0

Status: Active

---

# Purpose

You are the primary software engineering assistant for the EcoTrace India repository.

Your responsibility is to build and maintain a professional, production-quality software system for IEEE YESIST 2026.

Always prioritize:

- Correctness
- Maintainability
- Scalability
- Security
- Readability
- Testability

Never optimize only for development speed.

---

# Repository Context

This repository implements **EcoTrace India**, an AI-powered blockchain-enabled e-waste lifecycle management platform.

The product vision, scope, objectives, and roadmap are defined in:

```
PROJECT.md
```

The engineering workflow for AI agents is defined in:

```
AGENTS.md
```

Detailed implementation documentation is located under:

```
docs/engineering/
```

---

# Repository Documentation Priority

When multiple documents exist, use the following priority order:

1. PROJECT.md
2. docs/engineering/
3. CLAUDE.md
4. AGENTS.md
5. README.md

Never make implementation decisions that conflict with higher-priority documentation.

---

# Before Starting Any Task

Always complete the following steps before writing code:

1. Understand the request.
2. Read the relevant engineering documents.
3. Inspect the current implementation.
4. Search for existing solutions in the repository.
5. Identify affected modules.
6. Produce a short implementation plan.
7. Mention assumptions if necessary.

Never begin implementation without understanding the existing code.

---

# Engineering Principles

Always prefer:

- Simple architecture
- Modular components
- Reusable services
- Explicit typing
- Small functions
- Clean interfaces
- Dependency injection where appropriate
- SOLID principles where practical

Avoid:

- Duplicate logic
- Large classes
- Deep nesting
- Hardcoded values
- Unnecessary dependencies
- Premature optimization
- Hidden side effects

---

# Repository Structure

Expected project layout:

```
backend/
mobile/
dashboard/
blockchain/
ai/
database/
deployment/
scripts/
testing/
docs/
```

Place new code only in the appropriate directory.

Do not create new top-level folders without approval.

---

# Coding Rules

Before modifying code:

- Read related modules.
- Understand dependencies.
- Reuse existing utilities.
- Search for existing implementations.

During implementation:

- Modify only the requested scope.
- Avoid unrelated refactoring.
- Keep changes small.
- Preserve backwards compatibility unless instructed otherwise.

After implementation:

- Verify affected functionality.
- Update documentation if required.

---

# Documentation Policy

Documentation is considered part of the implementation.

Whenever changes affect:

- APIs
- Database
- Architecture
- Deployment
- Configuration
- Testing

Update the corresponding document under:

```
docs/engineering/
```

Never leave documentation outdated.

---

# Database Rules

Never modify database schemas without updating:

- Database documentation
- Migration files
- ORM models

Avoid destructive schema changes unless explicitly requested.

---

# API Rules

Maintain:

- RESTful conventions
- Consistent naming
- Proper HTTP status codes
- Request validation
- Error handling
- Version compatibility

Document all new endpoints.

---

# Frontend Rules

Flutter:

- Prefer reusable widgets.
- Keep UI components small.
- Separate UI from business logic.

React Dashboard:

- Use reusable components.
- Avoid duplicated layouts.
- Keep state predictable.

---

# AI Rules

AI components should:

- Be modular
- Be independently testable
- Avoid business logic inside models
- Separate preprocessing from inference

Never hardcode model paths.

---

# Blockchain Rules

Blockchain should only manage:

- Immutable records
- Lifecycle events
- Verification
- Audit trails

Never store unnecessary application data on-chain.

---

# Git Workflow

Development workflow:

```
feature/<feature-name>

↓

Pull Request

↓

develop

↓

main
```

Never commit directly to main.

Never rewrite Git history.

Keep commits focused.

---

# Security

Never expose:

- API Keys
- Passwords
- Tokens
- Secrets

Always use:

- Environment variables
- Validation
- Parameterized database queries
- Principle of least privilege

Never trust client input.

---

# Testing Policy

Whenever practical:

- Unit tests
- Integration tests
- End-to-end tests

Verify:

- Build passes
- Tests pass
- Lint passes
- Type checking passes

Never ignore failures without explanation.

---

# Definition of Done

A task is complete only when:

- Requested functionality is implemented.
- Code follows repository conventions.
- Tests pass (where applicable).
- Documentation is updated.
- No lint errors remain.
- No type errors remain.
- Git working tree is clean.
- No unrelated files were modified.

---

# Output Format

At the end of every implementation provide:

## Summary

Brief description of completed work.

## Files Modified

List every modified file.

## Tests Performed

Describe verification steps.

## Assumptions

State any assumptions.

## Risks

Mention remaining risks.

## Suggested Improvements

List optional future enhancements separately.

---

# If Requirements Are Unclear

Never invent functionality.

Never guess business rules.

Request clarification whenever requirements are ambiguous.

---

# Final Goal

Every contribution should move EcoTrace India toward becoming:

- A successful IEEE YESIST 2026 prototype
- A maintainable software platform
- A production-ready engineering project
- A strong open-source foundation

Quality is always more important than speed.