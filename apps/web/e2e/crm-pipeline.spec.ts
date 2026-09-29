/*
 * SKY-94: End-to-end test for the CRM deal pipeline.
 *
 * Validates:
 *   A) API error paths for invalid stage transitions (no UI needed).
 *   B) Qualified-lead → opportunity creation via API.
 *   C) Walking prospecting → qualified → proposal → negotiation → won
 *      through the opportunity board UI using quick-move buttons.
 *
 * Strategy: the board is re-rendered after every move — assertions locate
 * the card by name inside the target section to decouple from transient
 * loading skeletons.
 *
 * Serial single test — see AGENTS.md.  The workspace fixture creates a
 * fresh browser context and authenticates via the UI, so it never
 * collides with the reports-smoke suite's token family.
 */

import { expect } from "@playwright/test";

import { test } from "./fixtures/auth";
import {
    BffError,
    BffApi,
    seedLead,
    qualifyLead,
    changeOpportunityStage,
    getOpportunity,
} from "./helpers/api";

test("crm deal pipeline: validate API errors and walk prospecting → won through the board", async ({
    workspace,
}) => {
    const { page } = workspace;
    const api = new BffApi(page.request);
    const timestamp = Date.now();
    const mainName = `Acme Corp ${timestamp}`;

    // ------------------------------------------------------------------
    // A) API error paths — run on a side opportunity so the main pipeline
    //    card never hits a failed transition.
    // ------------------------------------------------------------------
    const sideLead = await seedLead(api, `Side Co ${timestamp}`);
    const sideOpp = await qualifyLead(api, sideLead.id);
    expect(sideOpp.stage).toBe("prospecting");

    await test.step("forward skip (prospecting → proposal) is rejected", async () => {
        const error = await api
            .post(`/api/v1/crm/opportunities/${sideOpp.id}/stage`, {
                stage: "proposal",
            })
            .then(
                () => null,
                (err) => err as BffError,
            );

        expect(error).not.toBeNull();
        expect(error!.message).toContain(
            "Cannot move opportunity from 'prospecting' to 'proposal'",
        );
    });

    await test.step("same-stage move is rejected", async () => {
        const error = await api
            .post(`/api/v1/crm/opportunities/${sideOpp.id}/stage`, {
                stage: "prospecting",
            })
            .then(
                () => null,
                (err) => err as BffError,
            );

        expect(error).not.toBeNull();
        expect(error!.message).toContain(
            "Opportunity is already in stage 'prospecting'",
        );
    });

    await test.step("won is allowed from any non-terminal stage", async () => {
        const result = await changeOpportunityStage(api, sideOpp.id, "won");
        expect(result.stage).toBe("won");
    });

    await test.step("terminal state rejects further moves", async () => {
        const error = await api
            .post(`/api/v1/crm/opportunities/${sideOpp.id}/stage`, {
                stage: "lost",
            })
            .then(
                () => null,
                (err) => err as BffError,
            );

        expect(error).not.toBeNull();
        expect(error!.message).toContain(
            "Opportunity already terminated in stage 'won'",
        );
    });

    // ------------------------------------------------------------------
    // B) Seed the main pipeline opportunity via qualifying a lead.
    // ------------------------------------------------------------------
    const mainLead = await seedLead(api, mainName);
    const mainOpp = await qualifyLead(api, mainLead.id);
    expect(mainOpp.stage).toBe("prospecting");

    // ------------------------------------------------------------------
    // C) Walk prospecting → won through the board UI.
    // ------------------------------------------------------------------
    const forwardMoves = [
        {
            next: "Qualified",
            stage: "qualified",
            title: "Move to Qualified?",
            confirm: "Move forward",
        },
        {
            next: "Proposal",
            stage: "proposal",
            title: "Move to Proposal?",
            confirm: "Move forward",
        },
        {
            next: "Negotiation",
            stage: "negotiation",
            title: "Move to Negotiation?",
            confirm: "Move forward",
        },
    ];

    await test.step("verify card appears at prospecting", async () => {
        await page.goto("/dashboard/erp/crm/opportunities");
        const card = page.locator("article").filter({ hasText: mainName });
        await expect(card).toBeVisible();
        await expect(
            page
                .locator('section[aria-label="Prospecting"]')
                .locator("article")
                .filter({ hasText: mainName }),
        ).toBeVisible();
    });

    for (const { next, stage, title, confirm } of forwardMoves) {
        await test.step(`move to ${next}`, async () => {
            const card = page.locator("article").filter({ hasText: mainName });
            // The quick-move footer button is labelled by the target stage name.
            await card.getByRole("button", { name: next, exact: true }).click();

            const dialog = page.getByRole("dialog", { name: title });
            await expect(dialog).toBeVisible();
            await dialog.getByRole("button", { name: confirm }).click();
            await expect(dialog).not.toBeVisible();

            // Wait for the card to land in the target column.
            await expect(
                page
                    .locator(`section[aria-label="${next}"]`)
                    .locator("article")
                    .filter({ hasText: mainName }),
            ).toBeVisible();

            // The column assertion above only proves the board RENDERED the
            // move. A board that re-read the row before the write committed
            // would pass it while persisting nothing, so confirm the move
            // actually stuck server-side.
            expect((await getOpportunity(api, mainOpp.id)).stage).toBe(stage);
        });
    }

    await test.step("move to won (terminal)", async () => {
        const card = page.locator("article").filter({ hasText: mainName });
        await card.getByRole("button", { name: "Won", exact: true }).click();

        const dialog = page.getByRole("dialog", { name: "Mark as won?" });
        await expect(dialog).toBeVisible();
        await dialog.getByRole("button", { name: "Mark won" }).click();
        await expect(dialog).not.toBeVisible();

        // Card lands in the Won column and shows the terminal badge.
        await expect(
            page
                .locator('section[aria-label="Won"]')
                .locator("article")
                .filter({ hasText: mainName }),
        ).toBeVisible();
        await expect(
            page
                .locator("article")
                .filter({ hasText: mainName })
                .getByText("Won", { exact: true }),
        ).toBeVisible();

        // Terminal cards have no quick-move buttons.
        await expect(
            page
                .locator("article")
                .filter({ hasText: mainName })
                .locator("footer button"),
        ).toHaveCount(0);

        expect((await getOpportunity(api, mainOpp.id)).stage).toBe("won");
    });

    // ------------------------------------------------------------------
    // D) Walk a second opportunity to lost through the board UI (with a
    //    lost reason in the confirm dialog).
    // ------------------------------------------------------------------
    const lostName = `Lost Co ${timestamp}`;
    const lostLead = await seedLead(api, lostName);
    const lostOpp = await qualifyLead(api, lostLead.id);
    expect(lostOpp.stage).toBe("prospecting");

    // Stage it to negotiation via API so the UI walk starts at the terminal
    // decision point (won/lost).
    await changeOpportunityStage(api, lostOpp.id, "qualified");
    await changeOpportunityStage(api, lostOpp.id, "proposal");
    await changeOpportunityStage(api, lostOpp.id, "negotiation");

    await test.step("move to lost with a reason", async () => {
        await page.goto("/dashboard/erp/crm/opportunities");
        const card = page.locator("article").filter({ hasText: lostName });
        await expect(card).toBeVisible();

        await card.getByRole("button", { name: "Lost", exact: true }).click();

        const dialog = page.getByRole("dialog", { name: "Mark as lost?" });
        await expect(dialog).toBeVisible();
        await dialog.locator("#lost-reason").fill("Went with a competitor");
        await dialog.getByRole("button", { name: "Mark lost" }).click();
        await expect(dialog).not.toBeVisible();

        // Card lands in the Lost column and shows the terminal badge.
        await expect(
            page
                .locator('section[aria-label="Lost"]')
                .locator("article")
                .filter({ hasText: lostName }),
        ).toBeVisible();
        await expect(
            page
                .locator("article")
                .filter({ hasText: lostName })
                .getByText("Lost", { exact: true }),
        ).toBeVisible();

        // Terminal cards have no quick-move buttons.
        await expect(
            page
                .locator("article")
                .filter({ hasText: lostName })
                .locator("footer button"),
        ).toHaveCount(0);

        // The lost reason entered in the dialog must have been persisted.
        const saved = await getOpportunity(api, lostOpp.id);
        expect(saved.stage).toBe("lost");
        expect(saved.lostReason).toBe("Went with a competitor");
    });
});
