"""R&D question A: does tool granularity change agent behaviour?

Run: MODEL_PROFILE=open_hosted python -m evals.runners.tool_granularity
40 tasks with a known correct capability and arguments. Three tool sets are offered to the
same model (the scout node's model, so the cheap-router setting):
  fine    many narrow tools (one per field / per evidence type)
  coarse  three multiplexed tools with an `action` argument
  best    the shipped MCP tool names with the rewritten descriptions from the servers
Metrics: tool-selection accuracy (first call is an acceptable tool), argument accuracy
(required argument values present), tokens per task. Writes evals/results/tool_granularity.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from agent.llm import get_llm

ROOT = Path(__file__).resolve().parents[2]

# capability, task text, expected argument substrings (lower-case) keyed by meaning
TASKS: list[tuple[str, str, dict[str, str]]] = [
    ("search_jobs", "Find new jobs that mention dbt.", {"query": "dbt"}),
    ("search_jobs", "Any Celery or Redis gigs posted today?", {"query": "celery"}),
    ("search_jobs", "Look for Next.js freelance work.", {"query": "next"}),
    ("search_jobs", "Search the marketplace for Power BI dashboard jobs.", {"query": "power bi"}),
    ("search_jobs", "Show me five LangGraph jobs.", {"query": "langgraph"}),
    ("get_job", "Open job job_9ae1ee56f0b1 so I can read the full post.", {"id": "job_9ae1ee56f0b1"}),
    ("get_job", "What budget does job_7ae85e6c4e7c have?", {"id": "job_7ae85e6c4e7c"}),
    ("get_job", "Read the description of job_913f71039141.", {"id": "job_913f71039141"}),
    ("get_client_history", "Is client c_0042 trustworthy? Check their history.", {"id": "c_0042"}),
    ("get_client_history", "What rating does client c_0107 have?", {"id": "c_0107"}),
    ("get_client_history", "Has client c_0311 verified their payment method?", {"id": "c_0311"}),
    ("get_client_history", "How much has client c_0005 spent on the platform?", {"id": "c_0005"}),
    ("get_connects_balance", "How many Connects do I have left?", {}),
    ("get_connects_balance", "Can I afford another proposal this week?", {}),
    ("get_connects_balance", "What is my weekly Connects budget?", {}),
    ("list_messages", "Show the messages in thread th_0001.", {"id": "th_0001"}),
    ("list_messages", "Did the client in thread th_0007 reply?", {"id": "th_0007"}),
    ("list_messages", "Read all my client conversations.", {}),
    ("search_evidence", "Do I have experience with Pinecone?", {"query": "pinecone"}),
    ("search_evidence", "Find proof that I have built RAG chatbots.", {"query": "rag"}),
    ("search_evidence", "Which of my projects used Stripe?", {"query": "stripe"}),
    ("search_evidence", "Find a past proposal that won for a dashboard job.", {"query": "dashboard"}),
    ("search_evidence", "What client reviews mention fast delivery?", {"query": "deliver"}),
    ("search_evidence", "Have I done computer vision for a manufacturing client?", {"query": "vision"}),
    ("search_evidence", "Show code in my repos that uses Kafka.", {"query": "kafka"}),
    ("search_evidence", "Evidence for Tableau work?", {"query": "tableau"}),
    ("get_case_study", "Open my case study support-rag-bot.", {"id": "support-rag-bot"}),
    ("get_case_study", "Give me the full write-up of the dbt-warehouse project.", {"id": "dbt-warehouse"}),
    ("get_case_study", "Show case study saas-billing-dashboard in full.", {"id": "saas-billing-dashboard"}),
    ("list_skills", "What skills are in my profile?", {}),
    ("list_skills", "Which skills do I have evidence for?", {}),
    ("list_skills", "List my skills.", {}),
    ("get_free_slots", "When am I free for a 30 minute interview this week?", {}),
    ("get_free_slots", "Suggest three interview times.", {}),
    ("create_tentative_hold", "Hold 2026-11-18T10:00:00Z for 30 minutes for the Acme interview.", {"start": "2026-11-18"}),
    ("create_tentative_hold", "Pencil in a 45 minute call on 2026-11-20T14:00:00Z with the client.", {"start": "2026-11-20"}),
    ("create_email_draft", "Draft an email to sam@example.com confirming the interview.", {"to": "sam@example.com"}),
    ("create_email_draft", "Write an email draft to lee@example.org with the project plan.", {"to": "lee@example.org"}),
    ("search_jobs", "Find remote data cleaning jobs.", {"query": "data clean"}),
    ("search_evidence", "Do I have any React Native work to show?", {"query": "react native"}),
]


def _tool(name: str, desc: str, **fields: Any) -> StructuredTool:
    model: type[BaseModel] = create_model(name + "_args", **fields)  # type: ignore[call-overload]
    return StructuredTool.from_function(func=lambda **_: "ok", name=name, description=desc,
                                        args_schema=model)


S, OS, I = (str, ...), (str | None, None), (int, 20)


def best_set() -> list[StructuredTool]:
    """Shipped tool names; descriptions copied from the MCP servers."""
    from mcp_servers.marketplace import server as m
    from mcp_servers.portfolio import server as p
    from mcp_servers.workspace import server as w

    d = lambda f: (f.__doc__ or "").strip()
    return [
        _tool("search_jobs", d(m.search_jobs), query=S, limit=I),
        _tool("get_job", d(m.get_job), job_id=S),
        _tool("get_client_history", d(m.get_client_history), client_id=S),
        _tool("get_connects_balance", d(m.get_connects_balance)),
        _tool("list_messages", d(m.list_messages), thread_id=OS),
        _tool("search_evidence", d(p.search_evidence), requirement=S, k=(int, 5)),
        _tool("get_case_study", d(p.get_case_study), id=S),
        _tool("list_skills", d(p.list_skills)),
        _tool("get_free_slots", d(w.get_free_slots), days_ahead=(int, 5)),
        _tool("create_tentative_hold", d(w.create_tentative_hold), start=S,
              duration_minutes=(int, 30), title=S, idempotency_key=S),
        _tool("create_email_draft", d(w.create_email_draft), to=S, subject=S, body=S,
              idempotency_key=S),
    ]


FINE_MAP = {
    "search_jobs": {"search_jobs_by_keyword", "search_jobs_by_skill"},
    "get_job": {"get_job_title", "get_job_budget", "get_job_description"},
    "get_client_history": {"get_client_rating", "get_client_spend", "get_client_payment_status",
                           "get_client_reviews"},
    "get_connects_balance": {"get_connects_balance", "get_weekly_connects_budget"},
    "list_messages": {"list_threads", "get_thread_messages"},
    "search_evidence": {"search_case_studies", "search_repos", "search_code", "search_reviews",
                        "search_past_proposals", "search_cv"},
    "get_case_study": {"get_case_study_text", "get_case_study_metadata"},
    "list_skills": {"list_skills", "list_evidenced_skills"},
    "get_free_slots": {"get_free_slots"},
    "create_tentative_hold": {"create_calendar_hold"},
    "create_email_draft": {"create_email_draft"},
}


def fine_set() -> list[StructuredTool]:
    out = []
    for names in FINE_MAP.values():
        for n in sorted(names):
            fields: dict[str, Any] = {}
            if n.startswith(("search_", "get_job", "get_client", "get_case", "get_thread")):
                key = ("query" if n.startswith("search_") else "id")
                fields[key] = S
            if n == "create_calendar_hold":
                fields = {"start": S, "duration_minutes": (int, 30)}
            if n == "create_email_draft":
                fields = {"to": S, "subject": S, "body": S}
            out.append(_tool(n, n.replace("_", " ").capitalize() + ".", **fields))
    return out


COARSE_MAP = {"search_jobs": ("marketplace", "search"), "get_job": ("marketplace", "get_job"),
              "get_client_history": ("marketplace", "client"),
              "get_connects_balance": ("marketplace", "connects"),
              "list_messages": ("marketplace", "messages"),
              "search_evidence": ("portfolio", "search"), "get_case_study": ("portfolio", "case"),
              "list_skills": ("portfolio", "skills"), "get_free_slots": ("workspace", "slots"),
              "create_tentative_hold": ("workspace", "hold"),
              "create_email_draft": ("workspace", "email")}


def coarse_set() -> list[StructuredTool]:
    return [
        _tool("marketplace", "Marketplace operations. action: search | get_job | client | "
              "connects | messages.", action=S, query=OS, id=OS),
        _tool("portfolio", "Portfolio operations. action: search | case | skills.",
              action=S, query=OS, id=OS),
        _tool("workspace", "Calendar and email. action: slots | hold | email.",
              action=S, start=OS, to=OS, text=OS),
    ]


def judge(setname: str, cap: str, call: dict | None, expect: dict[str, str]) -> tuple[bool, bool]:
    if call is None:
        return False, False
    name, args = call["name"], {k: str(v).lower() for k, v in (call.get("args") or {}).items()}
    if setname == "best":
        ok_tool = name == cap
    elif setname == "fine":
        ok_tool = name in FINE_MAP[cap]
    else:
        tool, action = COARSE_MAP[cap]
        ok_tool = name == tool and args.get("action", "") == action
    blob = " ".join(args.values())
    ok_args = ok_tool and all(v.lower() in blob for v in expect.values())
    return ok_tool, ok_args


def main() -> None:
    llm = get_llm("scout")
    system = ("You are a freelancer's assistant. Call exactly one tool that best answers the "
              "request. Do not answer in text.")
    sets = {"fine": fine_set(), "coarse": coarse_set(), "best": best_set()}
    results: dict[str, Any] = {}
    for setname, tools in sets.items():
        bound = llm.bind_tools(tools)
        rows, tokens = [], 0
        for cap, text, expect in TASKS:
            call, used = None, 0
            for attempt in range(3):
                try:
                    msg = bound.invoke([SystemMessage(content=system), HumanMessage(content=text)])
                    used = int((msg.usage_metadata or {}).get("total_tokens", 0))
                    call = msg.tool_calls[0] if msg.tool_calls else None
                    break
                except Exception:  # noqa: BLE001 - rate limits: back off and retry
                    time.sleep(5 * (attempt + 1))
            ok_tool, ok_args = judge(setname, cap, call, expect)
            tokens += used
            rows.append({"task": text, "expected": cap, "called": call["name"] if call else None,
                         "args": call.get("args") if call else None,
                         "tool_ok": ok_tool, "args_ok": ok_args, "tokens": used})
        n = len(rows)
        results[setname] = {"tools": len(tools), "tasks": n,
                            "tool_selection_accuracy": round(sum(r["tool_ok"] for r in rows) / n, 4),
                            "argument_accuracy": round(sum(r["args_ok"] for r in rows) / n, 4),
                            "tokens_per_task": round(tokens / n, 1), "rows": rows}
        print(setname, {k: v for k, v in results[setname].items() if k != "rows"}, flush=True)
    from agent.config import get_config

    out = {"model": get_config().models.profiles[get_config().models.profile]["scout"].model,
           "profile": get_config().models.profile, "results": results}
    (ROOT / "evals/results/tool_granularity.json").write_text(json.dumps(out, indent=2,
                                                                         default=str),
                                                             encoding="utf-8")


if __name__ == "__main__":
    main()
