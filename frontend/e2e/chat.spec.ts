// End-to-end: a real browser against the real stack (with the scripted fake model, so answers are predictable).
import { expect, type Page, test } from "@playwright/test";

const password = process.env.E2E_PASSWORD ?? "";

async function logIn(page: Page, pw = password) {
  await page.goto("/");
  await page.getByLabel("Username").fill("demo");
  await page.getByLabel("Password").fill(pw);
  await page.getByRole("button", { name: "Log in" }).click();
}

async function openSupportWorkflow(page: Page) {
  await page.getByRole("combobox").selectOption({ label: "Support email workflow" });
  await page.getByRole("button", { name: "+ New conversation" }).click();
}

test.beforeAll(() => {
  if (!password) throw new Error("Set E2E_PASSWORD to the stack's DEMO_PASSWORD");
});

test("a wrong password is refused", async ({ page }) => {
  await logIn(page, "definitely-wrong");
  await expect(page.getByRole("alert")).toHaveText("Invalid username or password");
});

test("draft, approve and find the conversation again after a reload", async ({ page }) => {
  await logIn(page);
  await openSupportWorkflow(page);
  await page.getByRole("button", { name: "Moved abroad (EN)" }).click();

  await expect(page.getByText("Draft reply")).toBeVisible();
  await page.getByRole("button", { name: "approve" }).click();
  await expect(page.getByText("Sent:")).toBeVisible();

  await page.reload(); // token is kept for this tab; the transcript comes from the database
  await page.getByRole("combobox").selectOption({ label: "Support email workflow" });
  await page.getByRole("button", { name: /^Hello, my member number is 100871/ }).first().click();
  await expect(page.getByText("Sent:")).toBeVisible();
  await expect(page.getByRole("article", { name: "user message" })).toHaveCount(2);
});

test("a complaint is handed to a human", async ({ page }) => {
  await logIn(page);
  await openSupportWorkflow(page);
  await page.getByRole("button", { name: "Complaint (NL)" }).click();
  await expect(page.getByText("never answered by AI")).toBeVisible();

  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Beste heer De Vries, onze excuses.");
  await page.getByRole("textbox", { name: "Message", exact: true }).press("Enter");
  await expect(page.getByText("onze excuses").last()).toBeVisible();
  await expect(page.getByText("Sent:")).toBeVisible();
});

test("the weather agent answers", async ({ page }) => {
  await logIn(page);
  await page.getByRole("button", { name: "Umbrella in Utrecht?" }).click();
  await expect(page.getByText("(fake model)")).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
});
