/**
 * Frontend error taxonomy and user-safe copy.
 *
 * The BFF and the /api/v1 client both funnel failures through normalized
 * `ApiError`s. This module classifies a failure by HTTP status and owns the
 * user-facing copy for failures where showing backend detail would leak
 * internal architecture (transport errors, 5xx, rate limits). Validation,
 * conflict, session, and permission failures keep their (already
 * user-oriented) backend messages - generic copy there would be worse.
 *
 * Technical detail always remains available on `ApiError.detail` and in
 * developer logs; this module only decides what the browser renders.
 */

/** Failure categories the frontend understands. */
export type ErrorKind =
    | "network"
    | "timeout"
    | "service_unavailable"
    | "server_error"
    | "rate_limited"
    | "auth_required"
    | "forbidden"
    | "not_found"
    | "validation"
    | "conflict"
    | "unknown";

export const NETWORK_ERROR_MESSAGE =
    "Couldn't connect. Check your connection and try again.";

export const SERVICE_UNAVAILABLE_MESSAGE =
    "Skyrict is temporarily unavailable. Please try again in a moment.";

export const TIMEOUT_MESSAGE =
    "That took longer than expected. Please try again.";

export const RATE_LIMITED_MESSAGE =
    "You're doing that a little too quickly. Please wait a moment and try again.";

/**
 * Map an HTTP status (0 = the fetch never got a response) to its failure
 * category.
 */
export function classifyError(status: number | null): ErrorKind {
    switch (status) {
        case 0:
            return "network";
        case 408:
            return "timeout";
        case 429:
            return "rate_limited";
        case 401:
            return "auth_required";
        case 403:
            return "forbidden";
        case 404:
            return "not_found";
        case 409:
            return "conflict";
        case 422:
            return "validation";
        case 500:
        case 529:
            return "server_error";
        case 502:
        case 503:
            return "service_unavailable";
        case 504:
            return "timeout";
        default:
            return "unknown";
    }
}

/** True when re-running the same request is safe and likely to succeed. */
export function isRetryableErrorKind(kind: ErrorKind): boolean {
    return (
        kind === "network" ||
        kind === "timeout" ||
        kind === "service_unavailable" ||
        kind === "server_error" ||
        kind === "rate_limited"
    );
}

/** True when the status represents a retryable transport/server failure. */
export function isRetryableStatus(status: number | null): boolean {
    return isRetryableErrorKind(classifyError(status));
}

/**
 * User-safe copy for a status, or null when the backend's own message should
 * be shown instead (validation, conflict, session, permission, not-found -
 * those messages are written for users).
 */
export function errorUserMessage(status: number | null): string | null {
    switch (classifyError(status)) {
        case "network":
            return NETWORK_ERROR_MESSAGE;
        case "timeout":
            return TIMEOUT_MESSAGE;
        case "service_unavailable":
        case "server_error":
            return SERVICE_UNAVAILABLE_MESSAGE;
        case "rate_limited":
            return RATE_LIMITED_MESSAGE;
        default:
            return null;
    }
}

export interface LoadErrorPresentation {
    /** Short headline rendered above the message. */
    title: string;
    /** One or two calm sentences the user can act on. */
    message: string;
    /** Whether a Retry action is appropriate. */
    retryable: boolean;
}

/**
 * Turn a caught error into a contextual data-loading presentation. Failures
 * from `ApiError`s classify by status; anything else is treated as a
 * transport failure, since a non-ApiError from our fetch wrappers means the
 * request never produced a response.
 */
export function describeLoadError(
    error: unknown,
    context: {
        /** Short title, e.g. "Plans are temporarily unavailable". */
        title: string;
        /** Body copy for the retryable case. */
        retryableMessage: string;
    },
): LoadErrorPresentation {
    const status =
        typeof error === "object" &&
        error !== null &&
        "status" in error &&
        typeof (error as { status?: unknown }).status === "number"
            ? (error as { status: number }).status
            : 0;

    const kind = classifyError(status);
    if (kind === "validation" || kind === "conflict" || kind === "forbidden") {
        const message =
            error instanceof Error && error.message
                ? error.message
                : context.retryableMessage;
        return { title: context.title, message, retryable: false };
    }

    const userMessage = errorUserMessage(status);
    return {
        title: context.title,
        message: userMessage ?? context.retryableMessage,
        retryable: isRetryableErrorKind(kind),
    };
}