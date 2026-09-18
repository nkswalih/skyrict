/*
 * SKY-108 input-injection probes: the stack must fail closed, not 500.
 *
 * Tries SQLi / XSS-shaped input at read surfaces and asserts the backend
 * either rejects the request (< 500, typically 422/404/429) or, when it does
 * answer 200, never reflects the raw payload back into the response body.
 * Absence of a 500 is the leak-detector: a crash/DB-error status here is a
 * bug, not a security incident.
 */

import { expect } from "@playwright/test";

import { securityTest as test } from "../helpers/security-fixtures";

interface Probe {
    name: string;
    path: string;
    /* When true, a 200 response must not echo the raw marker string. */
    noEcho?: string;
}

const MARKER = "<script>alert(1)</script>";

const PROBES: Probe[] = [
    {
        name: "SQLi boolean tautology in CRM search",
        path: "/api/v1/crm/customers?search=%27%20OR%20%271%27%3D%271",
    },
    {
        name: "SQLi comment injection in CRM leads",
        path: "/api/v1/crm/leads?search=%27%20UNION%20SELECT%20NULL--",
    },
    {
        name: "XSS payload reflected into CRM search",
        path: `/api/v1/crm/customers?search=${encodeURIComponent(MARKER)}`,
        noEcho: MARKER,
    },
    {
        name: "encoded traversal through a UUID path slot",
        path: "/api/v1/crm/leads/..%2F..%2Fetc%2Fpasswd",
    },
];

for (const probe of PROBES) {
    test(`fails closed on ${probe.name}`, async ({ admin }) => {
        const result = await admin.api.raw<unknown>(probe.path);
        expect(
            result.status,
            `${probe.path} exploded with ${result.status}`,
        ).toBeLessThan(500);

        if (result.ok && probe.noEcho) {
            const body = JSON.stringify(result.payload);
            expect(body, `${probe.name} reflected the raw payload`).not.toContain(
                probe.noEcho,
            );
        }
    });
}