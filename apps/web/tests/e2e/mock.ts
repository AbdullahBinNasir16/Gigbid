import type { Page, Route } from "@playwright/test";

export type Calls = { approvals: any[]; settings: any[] };

const DRAFT =
  "Your help centre needs a chatbot that cites sources. I built a retrieval-augmented chatbot over 3,200 help-centre articles that deflected 38% of tickets.\n\nI would start by confirming scope. Which part matters most first?";

const approval = {
  thread_id: "t1:job_1",
  job_id: "job_1",
  title: "RAG chatbot for support docs",
  payload: {
    thread_id: "t1:job_1",
    kind: "proposal",
    draft: {
      job_id: "job_1",
      cover_letter: DRAFT,
      claims: [{ text: "I built a retrieval-augmented chatbot over 3,200 help-centre articles that deflected 38% of tickets.", evidence_ids: ["case:ai_ml:support-rag-bot#2"], support: "supported" }],
    },
    evidence: [{ id: "case:ai_ml:support-rag-bot#2", type: "case_study", project: "support-rag-bot", source: "case_studies/support-rag-bot.md", text: "Customer support RAG chatbot. Result: cut first-response time from 9 hours to 40 seconds and deflected 38% of tickets." }],
    risk: { score: 0.1, flags: [], explanation: "client has no spend history" },
    price: { amount: 850, budget_type: "fixed", rationale: "client range 500-1000 fixed", connects_cost: 6, worth_it: true },
    compliance: { verdict: "pass", reasons: [], removed_items: [] },
    preview: { action: "submit_proposal", payload: {}, connects_cost: 6, connects_balance_after: 114 },
  },
};

export async function mockApi(page: Page, opts: { marketplace?: "ok" | "unavailable" } = {}): Promise<Calls> {
  const calls: Calls = { approvals: [], settings: [] };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === "/api/health")
      return json(route, opts.marketplace === "unavailable"
        ? { status: "degraded", marketplace: "unavailable", marketplace_detail: "Unavailable: marketplace unreachable", queued: 2 }
        : { status: "ok", marketplace: "ok", queued: 0 });
    if (p === "/api/auth/login" || p === "/api/auth/signup") return json(route, { token: "test-token" });
    if (p === "/api/auth/me")
      return json(route, { user_id: "u1", username: "reviewer", settings: { persona: "ai_ml", autonomy: "suggest", hourly_floor: null, weekly_connects_budget: 80, saved_searches: ["rag"], marketplace: "gigsim" } });
    if (p === "/api/auth/settings" && method === "PUT") {
      calls.settings.push(route.request().postDataJSON());
      return json(route, { user_id: "u1", username: "reviewer", settings: route.request().postDataJSON() });
    }
    if (p === "/api/jobs")
      return json(route, [{ job_id: "job_1", title: "RAG chatbot for support docs", category: "ai_ml", budget_type: "fixed", budget_min: 500, budget_max: 1000, connects_cost: 6, decision: "bid", fit: 0.74, risk: 0.1, risk_flags: [], price: 850, status: "awaiting_approval", thread_id: "t1:job_1" },
                          { job_id: "job_2", title: "Earn $500/week, pay outside platform", category: "other", budget_type: "fixed", budget_min: 500, budget_max: 500, connects_cost: 4, decision: "skip", fit: 0.05, risk: 0.96, risk_flags: ["off_platform_payment", "free_work"], price: null, status: "done", thread_id: "t1:job_2" }]);
    if (p === "/api/approvals/t1:job_1" || p === "/api/approvals/t1%3Ajob_1") {
      if (method === "POST") {
        calls.approvals.push(route.request().postDataJSON());
        return json(route, { ok: true, thread_id: "t1:job_1" });
      }
      return json(route, approval);
    }
    if (p.startsWith("/api/runs/") && p.endsWith("/trace")) return json(route, []);
    if (p.startsWith("/api/memory/")) return json(route, []);
    return json(route, {});
  });
  await page.route("**/api/runs/**/stream**", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: 'data: {"type":"node","node":"submit","summary":"proposal submitted"}\n\n' }));
  return calls;
}

export async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("reviewer");
  await page.getByLabel("Password").fill("reviewer-pass");
  await page.getByRole("button", { name: "Sign in" }).click();
}
