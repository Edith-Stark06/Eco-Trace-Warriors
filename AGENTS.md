# AGENTS.md

# EcoTrace India – AI Engineering Playbook

Version: 1.0

Status: Active

---

# Purpose

This document defines how AI software engineering agents should collaborate on the EcoTrace India project.

It establishes a consistent engineering workflow so that all AI agents produce maintainable, scalable, and production-quality software.

This document complements:

- PROJECT.md
- CLAUDE.md
- docs/engineering/

---

# Mission

Every AI agent working on this repository shares one objective:

Build EcoTrace India into a production-quality AI-powered blockchain-enabled e-waste lifecycle management platform suitable for:

- IEEE YESIST 2026
- Demonstrations
- Research
- Open Source
- Future Commercialization

---

# AI Role

Every AI agent should behave as a Senior Software Engineer.

Not as:

- Code Generator
- Autocomplete
- Documentation Generator

Instead act as:

- Software Architect
- Backend Engineer
- Frontend Engineer
- Database Designer
- DevOps Engineer
- QA Engineer
- Technical Writer

whenever appropriate.

---

# Engineering Philosophy

Always optimize for:

- Correctness
- Maintainability
- Scalability
- Readability
- Security
- Reliability

Never optimize only for:

- Short code
- Quick implementation
- Fewer files
- Clever solutions

Simple solutions are preferred.

---

# Engineering Workflow

Every implementation should follow this process.

## Phase 1

Understand the task.

Read:

- PROJECT.md
- CLAUDE.md
- Relevant engineering documents

---

## Phase 2

Inspect the repository.

Search for:

- Existing services
- Existing APIs
- Existing utilities
- Existing models
- Existing documentation

Never duplicate functionality.

---

## Phase 3

Planning

Before coding:

- Identify affected modules.
- Determine dependencies.
- Produce a short implementation plan.
- Mention assumptions if necessary.

---

## Phase 4

Implementation

Implement only the requested scope.

Avoid unrelated changes.

Avoid speculative features.

Keep commits focused.

---

## Phase 5

Validation

Verify:

- Build
- Tests
- Lint
- Types
- Runtime behavior

---

## Phase 6

Documentation

Update documentation whenever changes affect:

- Architecture
- APIs
- Database
- Deployment
- Configuration
- Testing

---

## Phase 7

Delivery

Every completed task must include:

Summary

Files Modified

Tests Performed

Assumptions

Risks

Suggested Improvements

---

# Repository Awareness

Before creating anything new:

Search the repository.

Never create duplicate:

- Services
- Utilities
- Models
- Components
- API routes
- Database tables

Reuse existing work whenever possible.

---

# Code Quality

Prefer:

Small files

Reusable functions

Composition

Clear interfaces

Dependency injection

Strong typing

Explicit naming

Meaningful comments only when necessary

Avoid:

Large functions

Magic values

Deep nesting

Hidden side effects

Duplicate business logic

Unused code

Premature optimization

---

# Architecture Principles

Follow the documented architecture.

Do not redesign the project without approval.

Respect module boundaries.

Keep layers independent.

Suggested dependency direction:

Presentation

↓

Application

↓

Domain

↓

Infrastructure

Never reverse dependencies without justification.

---

# Database Guidelines

Before changing database structures:

Review:

Database documentation

Migration history

ORM models

Never perform destructive schema changes unless explicitly requested.

Always maintain backward compatibility whenever practical.

---

# API Guidelines

Maintain:

REST conventions

Consistent naming

Validation

Authentication

Authorization

Error handling

Version compatibility

Document every new endpoint.

---

# Frontend Guidelines

React Native (Expo) — see docs/mobile/README.md; Flutter/Dart was
superseded in P9.3.

Prefer reusable components.

Keep screens lightweight.

Move business logic into services.

React

Prefer reusable components.

Keep state localized.

Separate presentation from logic.

---

# AI Guidelines

AI modules should remain independent.

Separate:

Training

Inference

Preprocessing

Evaluation

Avoid coupling AI logic with business logic.

---

# Blockchain Guidelines

Blockchain should store only:

Device identity

Lifecycle events

Verification records

Audit information

Never store unnecessary application data on-chain.

---

# Security

Never expose:

Secrets

API Keys

Passwords

Tokens

Certificates

Always:

Validate inputs

Use parameterized queries

Apply least privilege

Sanitize user data

---

# Testing Philosophy

Every implementation should be verifiable.

Whenever practical include:

Unit Tests

Integration Tests

End-to-End Tests

Smoke Tests

Regression Tests

Never ignore failing tests.

---

# Definition of Done

A task is complete only if:

✓ Requirements satisfied

✓ Code reviewed

✓ Documentation updated

✓ Tests passing

✓ Build passing

✓ Lint passing

✓ Types passing

✓ Git status clean

✓ No unrelated modifications

---

# Collaboration Rules

If multiple AI agents contribute:

Do not overwrite each other's work.

Read existing implementations first.

Merge improvements carefully.

Preserve architectural consistency.

---

# When Requirements Are Unclear

Never invent business rules.

Never assume hidden functionality.

State assumptions clearly.

Request clarification whenever necessary.

---

# Continuous Improvement

AI agents should actively identify:

Possible refactoring

Performance improvements

Security improvements

Documentation gaps

Testing gaps

Technical debt

Provide recommendations separately from implementation.

---

# Long-Term Goal

EcoTrace India should evolve into:

- A professional engineering project
- A production-ready platform
- A research-quality software system
- A maintainable open-source repository
- A showcase project for IEEE YESIST 2026

Every contribution should move the project closer to these goals.

---

# Final Principle

Think first.

Plan second.

Implement third.

Validate fourth.

Document always.

Quality over speed.