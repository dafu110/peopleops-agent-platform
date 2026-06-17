# AI Coding Workflow

This project is intentionally maintained as an AI-coding-friendly codebase.

## Workflow

1. Use AI coding tools for fast scaffolding of modules, tests, and documentation.
2. Keep generated changes small enough to review.
3. Run unit tests after each architectural slice.
4. Add tests around routing, PII redaction, tool execution, and data normalization.
5. Treat AI output as a draft: review security, persistence, error handling, and user-facing text before shipping.

## Current Examples

- `core/workflow.py`: LangGraph routing and tool orchestration.
- `core/tools.py`: tool adapter abstraction with local persisted artifacts.
- `core/rag_engine.py`: persistent Chroma index with manifest-based invalidation.
- `tests/test_core.py`: regression tests that capture behavior added during AI-assisted iteration.

## Interview Talking Points

- AI coding was used to accelerate implementation, but the project keeps explicit engineering guardrails.
- The code separates product workflow from cross-cutting services such as audit, redaction, and persistence.
- Tests act as a contract so AI-assisted refactors do not silently break routing or tool behavior.
