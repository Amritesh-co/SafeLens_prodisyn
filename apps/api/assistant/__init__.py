"""
SafeLens AI Assistant.

A retrieval-augmented question-answering agent over the SafeLens database.
The LLM (served by Ollama) never touches the database directly: it can only
call the fixed, read-only, tenant/role-scoped tools defined in `tools.py`.
"""
