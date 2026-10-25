"use client";

import { usePathname } from "next/navigation";
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";

import type { AuthUser } from "@/lib/api/auth-api";
import { ensureSession } from "@/lib/api/http";
import { clearModuleAccess } from "@/lib/access/modules";
import { clearResourceCache } from "@/lib/cache/resource-cache";
import { browserSigninUrl } from "@/lib/auth/client-urls";
import { getAccessToken, setAccessToken } from "@/lib/auth/session-store";

export type SessionStatus = "loading" | "authenticated" | "unauthenticated";

interface SessionContextValue {
    status: SessionStatus;
    user: AuthUser | null;
    /** Re-hydrate the in-memory access token + profile from the BFF. */
    restore: () => Promise<void>;
    /** Replace the in-memory profile (e.g. after an avatar change). */
    updateUser: (user: AuthUser) => void;
    logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    // The public demo is a session-free marketing surface: hydrating the BFF
    // session there leaked `/api/auth/session` traffic into the walkthrough.
    const isDemo = pathname?.startsWith("/demo") ?? false;
    const [status, setStatus] = useState<SessionStatus>(isDemo ? "unauthenticated" : "loading");
    const [user, setUser] = useState<AuthUser | null>(null);

    const restore = useCallback(async () => {
        try {
            // Single-flight with the /api/v1 client: exactly one server-side token
            // rotation per page load, so parallel hydrations never race the refresh
            // token (a reuse would revoke the whole token family).
            const session = await ensureSession();
            if (session) {
                setAccessToken(session.accessToken);
                setUser((session.user as AuthUser | null) ?? null);
                setStatus("authenticated");
            } else {
                setAccessToken(null);
                setUser(null);
                setStatus("unauthenticated");
                // No session: any cached permission set AND any cached payload
                // belongs to a previous identity and must not be served to
                // the next one.
                clearModuleAccess();
                clearResourceCache();
            }
        } catch {
            setAccessToken(null);
            setUser(null);
            setStatus("unauthenticated");
            clearModuleAccess();
            clearResourceCache();
        }
    }, []);

    useEffect(() => {
        if (isDemo) {
            setAccessToken(null);
            setUser(null);
            setStatus("unauthenticated");
            return;
        }
        void restore();
    }, [restore, isDemo]);

    const logout = useCallback(async () => {
        try {
            await fetch("/api/auth/logout", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ accessToken: getAccessToken() }),
            });
        } catch {
            // Best-effort: the cookie is cleared client-side regardless.
        }
        setAccessToken(null);
        setUser(null);
        setStatus("unauthenticated");
        // Drop the permission + payload caches so the next user never
        // inherits either.
        clearModuleAccess();
        clearResourceCache();
        // Leave the workspace origin immediately so the user lands on the tenant's
        // signin surface instead of lingering on a page with no session.
        window.location.assign(browserSigninUrl());
    }, []);

    const updateUser = useCallback((next: AuthUser) => {
        setUser(next);
    }, []);

    const value = useMemo(
        () => ({ status, user, restore, updateUser, logout }),
        [status, user, restore, updateUser, logout],
    );

    return (
        <SessionContext.Provider value={value}>
            {children}
        </SessionContext.Provider>
    );
}

export function useSession(): SessionContextValue {
    const context = useContext(SessionContext);
    if (!context) {
        throw new Error("useSession must be used within a SessionProvider");
    }
    return context;
}
