"""Trace recorder mirroring SAS RAM's query telemetry shapes.

In production these records come free from RAM:
GET /toolCalls, /llmCalls, /retrievalCalls filtered by parentQueryId.
The demo writes the same shapes so the Governance view is a drop-in.
"""

from store import store, next_id, now_ms


class Trace:
    def __init__(self, agent: str, channel: str, prompt: str, session_id: str):
        self.rec = {
            "traceId": next_id("TRC"),
            "queryId": next_id("QRY"),
            "sessionId": session_id,
            "agent": agent,
            "channel": channel,
            "prompt": prompt,
            "answerPreview": "",
            "status": "running",
            "startedAt": now_ms(),
            "ms": 0,
            "toolCalls": [],
            "llmCalls": [],
            "retrievalCalls": [],
            "guardrails": [],
            "costUSD": 0.0,
        }

    def tool(self, tool: str, server: str, args: dict, result, ms: int, status: str = "ok"):
        self.rec["toolCalls"].append({
            "id": next_id("TC"), "tool": tool, "server": server,
            "args": args, "result": result, "ms": ms, "status": status,
        })
        return self

    def llm(self, purpose: str, prompt_preview: str, completion_preview: str,
            pt: int, ct: int, ms: int, model: str = "sovereign-llm (simulated)"):
        cost = round((pt * 0.9 + ct * 2.7) / 1_000_000, 6)  # illustrative rates
        self.rec["llmCalls"].append({
            "id": next_id("LC"), "model": model, "purpose": purpose,
            "promptPreview": prompt_preview, "completionPreview": completion_preview,
            "promptTokens": pt, "completionTokens": ct, "costUSD": cost, "ms": ms,
        })
        self.rec["costUSD"] = round(self.rec["costUSD"] + cost, 6)
        return self

    def retrieval(self, collection: str, query: str, chunks: list, ms: int):
        self.rec["retrievalCalls"].append({
            "id": next_id("RC"), "collection": collection, "query": query,
            "chunks": chunks, "ms": ms,
        })
        return self

    def guardrail(self, gtype: str, claims: list, verdict: str):
        self.rec["guardrails"].append({"type": gtype, "claims": claims, "verdict": verdict})
        return self

    def done(self, answer_preview: str, status: str = "completed"):
        self.rec["answerPreview"] = answer_preview[:220]
        self.rec["status"] = status
        self.rec["ms"] = now_ms() - self.rec["startedAt"]
        store.traces.append(self.rec)
        return self.rec
