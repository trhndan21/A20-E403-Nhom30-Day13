from __future__ import annotations

import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .tracing import langfuse, tracing_enabled
from .tracing import langfuse


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str
    ) -> AgentResult:

        started = time.perf_counter()

        print(">>> RUN CALLED")
        print(">>> TRACING ENABLED:", tracing_enabled())
        print(">>> LANGFUSE OBJ:", langfuse)

        # RAG 
        docs = retrieve(message)
        prompt = f"Feature={feature}\nDocs={docs}\nQuestion={message}"

        # ===== LLM =====
        response = self.llm.generate(prompt)

        # Metrics 
        latency_ms = int((time.perf_counter() - started) * 1000)
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        cost_usd = self._estimate_cost(tokens_in, tokens_out)

        quality_score = self._heuristic_quality(
            message, response.text, docs
        )

        # LANGFUSE TRACE 
        if langfuse:
            try:
                with langfuse.trace(
                    name="chat",
                    user_id=hash_user_id(user_id),
                    input=message,
                ) as trace:

                    trace.update(
                        output=response.text,
                        metadata={
                            "feature": feature,
                            "session_id": session_id,
                            "model": self.model,
                            "latency_ms": latency_ms,
                            "tokens_in": tokens_in,
                            "tokens_out": tokens_out,
                            "cost_usd": cost_usd,
                            "quality_score": quality_score,
                            "doc_count": len(docs),
                            "query_preview": summarize_text(message),
                        },
                    )

                print(">>> TRACE SENT")

            except Exception as e:
                print(">>> TRACE ERROR:", e)
        else:
            print(">>> LANGFUSE NOT INITIALIZED")

        # ===== Metrics system =====
        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    # ===== COST =====
    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    # ===== QUALITY =====
    def _heuristic_quality(
        self,
        question: str,
        answer: str,
        docs: list[str]
    ) -> float:

        score = 0.5

        if docs:
            score += 0.2

        if len(answer) > 40:
            score += 0.1

        if question.lower().split():
            if any(token in answer.lower() for token in question.lower().split()[:3]):
                score += 0.1

        if "[REDACTED" in answer:
            score -= 0.2

        return round(max(0.0, min(1.0, score)), 2)