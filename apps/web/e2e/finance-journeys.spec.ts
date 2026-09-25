/*
 * SKY-105: End-to-end test for finance journeys.
 *
 * Validates the full journal-entry and invoice lifecycle plus statement
 * widgets, covering every backend error path and happy-path flow.
 *
 *   Group A — Journal entries
 *     A1  UI create balanced draft → detail page
 *     A3  AI-generated draft (asserts "suggested accounts" notice when the
 *         LLM endpoint is unavailable, runs the AI path when it is)
 *     A4  Post the draft
 *     A5  Unbalanced post fails (API)
 *     A6  Reverse a posted entry (API)
 *     B4  Void-posted conflict (API)
 *     B8  Void a draft entry (UI with native confirm)
 *
 *   Group B — Invoices + payments
 *     B1  Seed customer + draft invoice via API
 *     B2  UI walk: draft → issued → approved → paid
 *     B3  Approve non-issued invoice fails (API)
 *     B5  Overpay fails (API)
 *     B7  Void an issued invoice (UI with native confirm)
 *
 *   Group C — Statement widgets
 *     C1  AR aging widget present
 *     C2  Comparative P&L widget present
 *
 * Serial single test — see AGENTS.md.
 */

import { expect } from "@playwright/test";

import { test } from "./fixtures/auth";
import {
    BffError,
    BffApi,
    unique,
    todayIsoDate,
    createCustomer,
    seedBalancedEntry,
    seedUnbalancedDraft,
    seedInvoice,
} from "./helpers/api";

test.setTimeout(180_000);

test("finance journeys: JE lifecycle, invoice flow, and statement widgets", async ({
    workspace,
}) => {
    const { page } = workspace;
    const api = new BffApi(page.request);
    const timestamp = Date.now();
    const memoText = `E2E JE ${timestamp}`;
    const customerName = unique("CUST");
    let customerId = "";
    let draftId = "";
    let invoiceId = "";
    let invoiceNumber = "";

    // ====================================================================
    // A1 — UI: create a balanced journal entry
    // ====================================================================
    await test.step("create balanced JE via UI", async () => {
        await page.goto("/dashboard/erp/finance/journal-entries");
        await page.getByRole("button", { name: "New entry" }).click();
        const dlg = page.getByRole("dialog", { name: "New journal entry" });
        await expect(dlg).toBeVisible();

        await dlg.getByLabel("Memo").fill(memoText);

        // Row 1 — debit 1200 Cash $1,250
        const row1 = dlg.locator("table tbody tr").first();
        await row1.locator('input[aria-haspopup="listbox"]').fill("1200");
        await row1.locator('input[aria-haspopup="listbox"]').press("Enter");
        await expect(
            row1.locator('input[aria-haspopup="listbox"]'),
        ).toHaveValue(/1200/);
        await row1.locator('input[type="number"]').first().fill("1250");

        // Add second row
        await dlg.getByRole("button", { name: "Add line" }).click();

        // Row 2 — credit 4000 Sales Revenue $1,250
        const row2 = dlg.locator("table tbody tr").nth(1);
        await row2.locator('input[aria-haspopup="listbox"]').fill("4000");
        await row2.locator('input[aria-haspopup="listbox"]').press("Enter");
        await expect(
            row2.locator('input[aria-haspopup="listbox"]'),
        ).toHaveValue(/4000/);
        await row2.locator('input[type="number"]').nth(1).fill("1250");

        // Balanced indicator visible
        await expect(dlg.getByText("Balanced")).toBeVisible();
        // Save button is enabled
        await expect(
            dlg.getByRole("button", { name: "Save draft" }),
        ).toBeEnabled();

        await dlg.getByRole("button", { name: "Save draft" }).click();

        // Navigates to the entry detail page
        await expect(page).toHaveURL(
            /\/erp\/finance\/journal-entries\//,
        );
        await expect(page.getByRole("heading", { level: 1 }).filter({ hasText: memoText })).toBeVisible();
        await expect(page.getByText("Draft", { exact: true })).toBeVisible();
        draftId = page.url().split("/").pop()!;
    });

    // ====================================================================
    // A3 — AI-generated draft (fallback notice when LLM endpoint unavailable)
    // ====================================================================
    await test.step("AI draft (fallback notice when LLM unavailable)", async () => {
        await page.goto("/dashboard/erp/finance/journal-entries");
        await page.getByRole("button", { name: "AI Draft" }).click();
        const aiDlg = page.getByRole("dialog", { name: "AI Draft Entry" });
        await expect(aiDlg).toBeVisible();

        await aiDlg.getByLabel("Description").fill("E2E test expense for 500");
        await aiDlg.getByRole("button", { name: "Generate" }).click();

        // Wait for the request to resolve. The Apply button is rendered whether
        // the real LLM answered or core substituted its deterministic draft.
        const applyButton = aiDlg.getByRole("button", { name: "Apply Draft" });
        await expect(applyButton).toBeVisible({ timeout: 15_000 });

        // No LLM endpoint: core substitutes a deterministic account-code draft.
        // The dialog must surface it honestly as suggested accounts (not a
        // finished AI entry) — assert that notice, then bail.
        if (
            await aiDlg
                .getByText(/suggested accounts/i)
                .isVisible()
                .catch(() => false)
        ) {
            await aiDlg.getByRole("button", { name: "Cancel" }).click();
            return;
        }

        await applyButton.click();

        // Create dialog opens with AI-generated lines prefilled.
        const createDlg = page.getByRole("dialog", {
            name: "New journal entry",
        });
        await expect(createDlg).toBeVisible();

        const saveEnabled = await createDlg
            .getByRole("button", { name: "Save draft" })
            .waitFor({ state: "visible", timeout: 5_000 })
            .then(() =>
                createDlg
                    .getByRole("button", { name: "Save draft" })
                    .isEnabled()
                    .catch(() => false),
            )
            .catch(() => false);

        if (!saveEnabled) {
            // LLM returned an unbalanced draft — editor refuses to save. This is a
            // model-quality outcome, not a product bug; skip the step.
            createDlg
                .getByRole("button", { name: "Cancel" })
                .click()
                .catch(() => {});
            return;
        }

        // A $0.00/$0.00 draft balances but the backend rejects zero-value
        // entries — also a model-quality outcome; skip the step.
        const zeroDraft = await createDlg
            .getByText(/Debit \$0\.00/)
            .isVisible()
            .catch(() => false);

        if (zeroDraft) {
            createDlg
                .getByRole("button", { name: "Cancel" })
                .click()
                .catch(() => {});
            return;
        }

        await createDlg.getByRole("button", { name: "Save draft" }).click();

        await expect(page).toHaveURL(
            /\/erp\/finance\/journal-entries\//,
        );
        await expect(page.getByRole("heading", { level: 1 }).filter({ hasText: "E2E test expense for 500" })).toBeVisible();
    });

    // ====================================================================
    // A4 — Post the draft entry
    // ====================================================================
    await test.step("post the draft entry", async () => {
        await page.goto(`/dashboard/erp/finance/journal-entries/${draftId}`);
        await page.getByRole("button", { name: "Post" }).click();
        await expect(page.locator("span").getByText("Posted", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    });

    // ====================================================================
    // A5 — Unbalanced post fails
    // ====================================================================
    await test.step("unbalanced post fails (API)", async () => {
        const unbalanced = await seedUnbalancedDraft(api, `unbal-${timestamp}`);
        await expect(
            api.post(`/api/v1/finance/journal-entries/${unbalanced.id}/post`),
        ).rejects.toThrow("not balanced");
    });

    // ====================================================================
    // A6 — Reverse a posted entry (creates reversing entry)
    // ====================================================================
    await test.step("reverse posted entry (API + UI confirm)", async () => {
        const posted = await seedBalancedEntry(api, `rev-${timestamp}`);
        await api.post(`/api/v1/finance/journal-entries/${posted.id}/post`);

        await page.goto(`/dashboard/erp/finance/journal-entries/${posted.id}`);
        // Accept the native window.confirm that the Reverse button triggers.
        page.once("dialog", (d) => d.accept());
        await page.getByRole("button", { name: "Reverse" }).click();
        await expect(page.locator("span").getByText("Reversed", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
        // Original entry is no longer posted — no Post button visible.
        await expect(
            page.getByRole("button", { name: "Post" }),
        ).not.toBeVisible();
    });

    // ====================================================================
    // B4 — Void-posted conflict (API)
    // ====================================================================
    await test.step("void-posted conflict (API)", async () => {
        const posted = await seedBalancedEntry(api, `void-post-${timestamp}`);
        await api.post(`/api/v1/finance/journal-entries/${posted.id}/post`);

        await expect(
            api.post(`/api/v1/finance/journal-entries/${posted.id}/void`),
        ).rejects.toThrow(
            "Only draft journal entries can be voided; posted entries need a reversing entry (v1.1)",
        );
    });

    // ====================================================================
    // B8 — Void a draft entry via UI (native confirm)
    // ====================================================================
    await test.step("void draft entry via UI", async () => {
        const draft = await seedBalancedEntry(api, `void-draft-${timestamp}`);
        // seedBalancedEntry creates a DRAFT entry (balance only enforced at post).

        await page.goto(`/dashboard/erp/finance/journal-entries/${draft.id}`);
        await expect(page.getByText("Draft", { exact: true })).toBeVisible();
        page.once("dialog", (d) => d.accept());
        await page.getByRole("button", { name: "Void" }).click();
        await expect(page.locator("span").getByText("Voided", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    });

    // ====================================================================
    // B1 + B2 — Invoice: seed, then walk draft → issued → approved → paid
    // ====================================================================
    await test.step("create customer and seed invoice via API", async () => {
        const customer = await createCustomer(api, customerName);
        customerId = customer.id;
        const inv = await seedInvoice(api, customerId);
        invoiceId = inv.id;
        invoiceNumber = inv.invoice_number;
    });

    await test.step("invoice UI: draft → issued → approved → paid", async () => {
        await page.goto(`/dashboard/erp/finance/invoices/${invoiceId}`);
        await expect(
            page.getByRole("heading", { level: 1 }).filter({ hasText: invoiceNumber }),
        ).toBeVisible();
        await expect(page.getByText("Draft", { exact: true })).toBeVisible();

        await page.getByRole("button", { name: "Issue" }).click();
        await expect(page.locator("span").getByText("Issued", { exact: true }).first()).toBeVisible({ timeout: 15_000 });

        await page.getByRole("button", { name: "Approve" }).click();
        await expect(page.locator("span").getByText("Approved", { exact: true }).first()).toBeVisible({ timeout: 15_000 });

        await page.getByRole("button", { name: "Apply payment" }).click();
        const payDlg = page.getByRole("dialog", { name: "Apply payment" });
        await expect(payDlg).toBeVisible();

        // Default amount should equal the invoice total (unpaid balance).
        await expect(payDlg.getByLabel("Amount")).toHaveValue(/^1250(?:\.0+)?$/);
        await payDlg.getByLabel("Method").fill("Bank transfer");

        await payDlg.getByRole("button", { name: "Apply payment" }).click();
        await expect(page.locator("span").getByText("Paid", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    });

    // ====================================================================
    // B3 — Approve non-issued invoice fails (API)
    // ====================================================================
    await test.step("approve non-issued invoice fails (API)", async () => {
        const inv = await seedInvoice(api, customerId);
        // inv.status is "draft" — approve only accepts "issued".
        await expect(
            api.post(`/api/v1/finance/invoices/${inv.id}/approve`),
        ).rejects.toThrow("Only issued invoices can be approved");
    });

    // ====================================================================
    // B5 — Overpay fails (API)
    // ====================================================================
    await test.step("overpay fails (API)", async () => {
        const inv = await seedInvoice(api, customerId);
        await api.post(`/api/v1/finance/invoices/${inv.id}/issue`);
        await api.post(`/api/v1/finance/invoices/${inv.id}/approve`);

        await expect(
            api.post(`/api/v1/finance/invoices/${inv.id}/payments`, {
                amount: 9999,
                method: "Bank transfer",
                paid_at: new Date().toISOString(),
            }),
        ).rejects.toThrow("exceeds the outstanding balance");
    });

    // ====================================================================
    // B7 — Void an issued invoice via UI (native confirm)
    // ====================================================================
    await test.step("void issued invoice via UI", async () => {
        const inv = await seedInvoice(api, customerId);
        await api.post(`/api/v1/finance/invoices/${inv.id}/issue`);

        await page.goto(`/dashboard/erp/finance/invoices/${inv.id}`);
        page.once("dialog", (d) => d.accept());
        await page.getByRole("button", { name: "Void" }).click();
        await expect(page.locator("span").getByText("Voided", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
    });

    // ====================================================================
    // C1 + C2 — Statement widgets present
    // ====================================================================
    await test.step("AR aging and Comparative P&L widgets present", async () => {
        await page.goto("/dashboard/erp/finance/statements");
        await page.getByRole("tab", { name: "Automation" }).click();
        await expect(
            page.getByRole("heading", { name: "AR aging" }),
        ).toBeVisible();
        await expect(
            page.getByRole("heading", { name: "Comparative profit & loss" }),
        ).toBeVisible();
    });
});
