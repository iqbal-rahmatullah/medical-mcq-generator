# Overview

FastAPI-based system for generating evidence-grounded multiple-choice questions using retrieval-augmented generation (RAG). The backend retrieves evidence from a knowledge corpus, generates questions with an LLM, and verifies grounding before logging results. A Next.js frontend streams questions over WebSocket and provides an interface for configuring topics and reviewing outputs.
