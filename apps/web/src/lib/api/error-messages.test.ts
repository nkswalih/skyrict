/**
 * Tests for the frontend error taxonomy and user-safe copy.
 *
 * These pin the status -> kind/retryable/copy contract that every error
 * surface (error toasts, load states, the pricing wizard) relies on. A change
 * here ripples into what users see, so the mapping is locked down explicitly.
 */

import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/http";
import {
    classifyError,
    describeLoadError,
    errorUserMessage,
    isRetryableErrorKind,
    isRetryableStatus,
    NETWORK_ERROR_MESSAGE,
    RATE_LIMITED_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
    TIMEOUT_MESSAGE,
} from "@/lib/api/error-messages";

describe("classifyError", () => {
    it("maps transport and server failures", () => {
        expect(classifyError(0)).toBe("network");
        expect(classifyError(408)).toBe("timeout");
        expect(classifyError(429)).toBe("rate_limited");
        expect(classifyError(500)).toBe("server_error");
        expect(classifyError(502)).toBe("service_unavailable");
        expect(classifyError(503)).toBe("service_unavailable");
        expect(classifyError(504)).toBe("timeout");
        expect(classifyError(529)).toBe("server_error");
    });

    it("maps user-actionable failures", () => {
        expect(classifyError(401)).toBe("auth_required");
        expect(classifyError(403)).toBe("forbidden");
        expect(classifyError(404)).toBe("not_found");
        expect(classifyError(409)).toBe("conflict");
        expect(classifyError(422)).toBe("validation");
    });

    it("falls back to unknown for anything else", () => {
        expect(classifyError(418)).toBe("unknown");
        expect(classifyError(null)).toBe("unknown");
        expect(classifyError(undefined as unknown as number)).toBe("unknown");
    });
});

describe("retryability", () => {
    it("treats transport/server failures as retryable", () => {
        for (const kind of [
            "network",
            "timeout",
            "service_unavailable",
            "server_error",
            "rate_limited",
        ] as const) {
            expect(isRetryableErrorKind(kind)).toBe(true);
        }
    });

    it("never retries mutations-worthy failure kinds", () => {
        for (const kind of [
            "auth_required",
            "forbidden",
            "not_found",
            "conflict",
            "validation",
            "unknown",
        ] as const) {
            expect(isRetryableErrorKind(kind)).toBe(false);
        }
    });

    it("isRetryableStatus follows the same map", () => {
        expect(isRetryableStatus(503)).toBe(true);
        expect(isRetryableStatus(0)).toBe(true);
        expect(isRetryableStatus(422)).toBe(false);
        expect(isRetryableStatus(401)).toBe(false);
    });
});

describe("errorUserMessage", () => {
    it("returns safe copy for transport/server failures", () => {
        expect(errorUserMessage(0)).toBe(NETWORK_ERROR_MESSAGE);
        expect(errorUserMessage(408)).toBe(TIMEOUT_MESSAGE);
        expect(errorUserMessage(504)).toBe(TIMEOUT_MESSAGE);
        expect(errorUserMessage(503)).toBe(SERVICE_UNAVAILABLE_MESSAGE);
        expect(errorUserMessage(500)).toBe(SERVICE_UNAVAILABLE_MESSAGE);
        expect(errorUserMessage(429)).toBe(RATE_LIMITED_MESSAGE);
    });

    it("returns null when the backend message should be shown", () => {
        expect(errorUserMessage(400)).toBeNull();
        expect(errorUserMessage(401)).toBeNull();
        expect(errorUserMessage(403)).toBeNull();
        expect(errorUserMessage(404)).toBeNull();
        expect(errorUserMessage(409)).toBeNull();
        expect(errorUserMessage(422)).toBeNull();
    });
});

describe("describeLoadError", () => {
    const context = {
        title: "Plans are temporarily unavailable",
        retryableMessage:
            "We couldn't load the latest plans right now. Take a moment and try again.",
    };

    it("presents a 503 as retryable with safe copy", () => {
        const error = new ApiError(503, "upstream broke");
        expect(describeLoadError(error, context)).toEqual({
            title: "Plans are temporarily unavailable",
            message: SERVICE_UNAVAILABLE_MESSAGE,
            retryable: true,
        });
    });

    it("treats a non-ApiError as a transport failure", () => {
        const presentation = describeLoadError(new Error("fetch failed"), context);
        expect(presentation.retryable).toBe(true);
        expect(presentation.message).toBe(NETWORK_ERROR_MESSAGE);
        // Never surface the raw TypeError text ("fetch failed") to the user.
        expect(presentation.message).not.toContain("fetch");
    });

    it("keeps backend messages for validation/conflict/forbidden but never retries", () => {
        expect(describeLoadError(new ApiError(422, "Email is required"), context)).toEqual({
            title: "Plans are temporarily unavailable",
            message: "Email is required",
            retryable: false,
        });
        expect(describeLoadError(new ApiError(409, "Plan already active"), context)).toEqual({
            title: "Plans are temporarily unavailable",
            message: "Plan already active",
            retryable: false,
        });
        expect(describeLoadError(new ApiError(403, "No permission"), context)).toEqual({
            title: "Plans are temporarily unavailable",
            message: "No permission",
            retryable: false,
        });
    });

    it("falls back to the contextual copy for a silent backend message", () => {
        const presentation = describeLoadError(
            new ApiError(422, ""),
            context,
        );
        expect(presentation.message).toBe(context.retryableMessage);
        expect(presentation.retryable).toBe(false);
    });
});