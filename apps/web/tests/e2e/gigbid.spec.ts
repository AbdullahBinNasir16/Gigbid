import { expect, test } from "@playwright/test";
import { mockApi, signIn } from "./mock";

test("onboarding: create an account, pick a persona and save settings", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/login");
  await page.getByRole("button", { name: /create an account/i }).click();
  await page.getByLabel("Username").fill("newuser");
  await page.getByLabel("Password").fill("secret-pass");
  await page.getByLabel(/persona/i).selectOption("data_analyst");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByLabel("Weekly Connects budget").fill("60");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(calls.settings[0].weekly_connects_budget).toBe(60);
});

test("approving a proposal sends an approve decision and opens the run", async ({ page }) => {
  const calls = await mockApi(page);
  await signIn(page);
  await expect(page.getByTestId("job-card").first()).toContainText("RAG chatbot");
  await page.getByRole("link", { name: "Review proposal" }).click();
  await expect(page.getByText("What will be sent")).toBeVisible();
  // evidence appears on keyboard focus of the claim
  const claim = page.locator(".ev-claim").first();
  await claim.focus();
  await expect(page.locator(".ev-pop.open")).toContainText("support-rag-bot");
  await page.getByTestId("approve").click();
  await expect(page).toHaveURL(/\/runs\//);
  expect(calls.approvals).toEqual([{ action: "approve" }]);
});

test("rejecting requires a reason and sends it", async ({ page }) => {
  const calls = await mockApi(page);
  await signIn(page);
  await page.goto("/studio/t1%3Ajob_1");
  await page.getByTestId("reject").click();
  await expect(page.getByRole("alert")).toContainText("Say why");
  expect(calls.approvals).toHaveLength(0);
  await page.getByTestId("reject-reason").fill("budget too low for the scope");
  await page.getByTestId("reject").click();
  await expect(page).toHaveURL(/\/runs\//);
  expect(calls.approvals[0]).toEqual({ action: "reject", reason: "budget too low for the scope" });
});

test("editing a draft sends the edited text for compliance re-check", async ({ page }) => {
  const calls = await mockApi(page);
  await signIn(page);
  await page.goto("/studio/t1%3Ajob_1");
  const editor = page.getByTestId("draft-editor");
  await editor.fill("Your support team answers the same questions daily. I built a RAG chatbot that deflected 38% of tickets.");
  await expect(page.getByTestId("approve")).toHaveText("Approve with my edits");
  await page.getByTestId("approve").click();
  await expect(page).toHaveURL(/\/runs\//);
  expect(calls.approvals[0].action).toBe("edit");
  expect(calls.approvals[0].edited_text).toContain("deflected 38%");
});

test("degraded mode: the banner says the marketplace is down and work is queued", async ({ page }) => {
  await mockApi(page, { marketplace: "unavailable" });
  await signIn(page);
  const banner = page.getByTestId("degraded-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Marketplace unavailable");
  await expect(banner).toContainText("2 job(s) queued");
});

test("scam jobs show risk flags and a skip recommendation in the inbox", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  const scam = page.getByTestId("job-card").filter({ hasText: "pay outside platform" });
  await expect(scam).toContainText("skip");
  await expect(scam).toContainText("off platform payment");
});
