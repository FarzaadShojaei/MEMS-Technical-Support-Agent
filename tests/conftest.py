"""Stub heavy optional deps so API-shape tests run without installing
chromadb / sentence-transformers / openai (CI installs them; this keeps
local quick-runs cheap too)."""
import sys
import types

for name in ("chromadb", "sentence_transformers", "openai"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            mod = types.ModuleType(name)
            if name == "sentence_transformers":
                mod.SentenceTransformer = object
            if name == "openai":
                mod.OpenAI = object
            sys.modules[name] = mod
