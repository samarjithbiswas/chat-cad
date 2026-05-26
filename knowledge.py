"""Knowledge store: TF-IDF retrieval over user notes + auto-captured designs.

A small RAG layer for the Design Agent. Three sources of knowledge:

1. Manual notes added via the UI ("we always use M4 bolts in this product").
2. Auto-captured records after every successful Design Agent run
   (the brief + final parts list + their materials).
3. .md / .txt files dropped into the knowledge_dir on startup.

Lookup is TF-IDF cosine similarity, fully in-process, no external services.
Good enough for ~hundreds of notes; not a vector DB.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections import Counter
from typing import Any


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


class KnowledgeStore:
    def __init__(self, store_dir: str):
        self.dir = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self.notes_path = os.path.join(store_dir, "_notes.json")
        self.notes: list[dict[str, Any]] = []
        self._idf: dict[str, float] = {}
        self._doc_vecs: list[dict[str, float]] = []
        self._doc_norms: list[float] = []
        self._load()

    # ----- persistence ----- #
    def _load(self) -> None:
        # 1. internal JSON notes
        if os.path.exists(self.notes_path):
            try:
                with open(self.notes_path, "r", encoding="utf-8") as f:
                    self.notes = json.load(f)
            except Exception:
                self.notes = []
        # 2. user-dropped files (.md, .txt)
        for fn in sorted(os.listdir(self.dir)):
            if fn.startswith("_"):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in (".md", ".txt"):
                continue
            full = os.path.join(self.dir, fn)
            if any(n.get("source") == fn for n in self.notes):
                continue
            try:
                with open(full, "r", encoding="utf-8") as f:
                    text = f.read()
                self.notes.append({
                    "id": f"file_{fn}",
                    "text": text.strip(),
                    "tags": ["file"],
                    "source": fn,
                    "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
            except Exception:
                pass
        self._rebuild_index()

    def _persist(self) -> None:
        try:
            with open(self.notes_path, "w", encoding="utf-8") as f:
                json.dump(self.notes, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ----- index ----- #
    def _rebuild_index(self) -> None:
        # tokenise each doc, compute IDF, then TF-IDF vectors with norms
        doc_tokens = [_tokenize(n["text"]) for n in self.notes]
        N = max(len(doc_tokens), 1)
        df: Counter = Counter()
        for tokens in doc_tokens:
            for t in set(tokens):
                df[t] += 1
        self._idf = {t: math.log((N + 1) / (c + 1)) + 1 for t, c in df.items()}

        self._doc_vecs = []
        self._doc_norms = []
        for tokens in doc_tokens:
            tf = Counter(tokens)
            vec = {t: (cnt / max(len(tokens), 1)) * self._idf.get(t, 0.0)
                   for t, cnt in tf.items()}
            self._doc_vecs.append(vec)
            self._doc_norms.append(math.sqrt(sum(v * v for v in vec.values())) or 1.0)

    def _query_vec(self, query: str) -> tuple[dict[str, float], float]:
        tokens = _tokenize(query)
        tf = Counter(tokens)
        vec = {t: (cnt / max(len(tokens), 1)) * self._idf.get(t, 0.0)
               for t, cnt in tf.items()}
        n = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return vec, n

    @staticmethod
    def _cosine(a: dict[str, float], a_norm: float,
                b: dict[str, float], b_norm: float) -> float:
        # dot over shorter dict
        small, large = (a, b) if len(a) < len(b) else (b, a)
        dot = sum(v * large.get(t, 0.0) for t, v in small.items())
        return dot / (a_norm * b_norm)

    # ----- public API ----- #
    def add(self, text: str, tags: list[str] | None = None,
            source: str = "manual") -> str:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty note")
        nid = source[:8] + "_" + uuid.uuid4().hex[:8]
        note = {
            "id": nid,
            "text": text,
            "tags": tags or [],
            "source": source,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.notes.append(note)
        self._rebuild_index()
        self._persist()
        return nid

    def remove(self, note_id: str) -> bool:
        before = len(self.notes)
        self.notes = [n for n in self.notes if n["id"] != note_id]
        if len(self.notes) != before:
            self._rebuild_index()
            self._persist()
            return True
        return False

    def list_notes(self) -> list[dict[str, Any]]:
        return [{"id": n["id"], "text": n["text"][:200],
                 "tags": n.get("tags", []), "source": n.get("source", ""),
                 "created": n.get("created", "")} for n in self.notes]

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        if not self.notes or not query.strip():
            return []
        qv, qn = self._query_vec(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for i, n in enumerate(self.notes):
            s = self._cosine(qv, qn, self._doc_vecs[i], self._doc_norms[i])
            if s > 0:
                scored.append((s, n))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [{"score": s, **n} for s, n in scored[:k]]

    def context_block(self, query: str, k: int = 5,
                      max_chars: int = 1500) -> str:
        """Format the top-K hits as a markdown block suitable for pasting
        into an LLM system prompt. Returns '' if nothing useful was found.
        """
        hits = self.search(query, k)
        if not hits:
            return ""
        out_lines = ["RELEVANT NOTES FROM YOUR KNOWLEDGE BASE:"]
        budget = max_chars
        for h in hits:
            line = f"- [{h['source']}] {h['text']}"
            if budget - len(line) < 0:
                break
            out_lines.append(line)
            budget -= len(line) + 1
        if len(out_lines) == 1:
            return ""
        out_lines.append("END OF NOTES.\n")
        return "\n".join(out_lines)
