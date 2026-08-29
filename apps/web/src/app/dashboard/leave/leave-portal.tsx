"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays, LoaderCircle, Send, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DatePicker } from "@/components/ui/date-picker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/http";
import {
  dismissLeaveSuggestion,
  getLeaveSuggestions,
  getPortalMe,
  listMyLeaveRequests,
  markSuggestionUsed,
  submitLeaveRequest,
  type PortalLeaveRequest,
  type PortalLeaveRequestStatus,
  type PortalLeaveSuggestion,
  type PortalMe,
} from "@/lib/api/portal-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type LoadState =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; me: PortalMe };

const STATUS_STYLES: Record<PortalLeaveRequestStatus, string> = {
  pending: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:text-amber-400",
  approved: "bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 dark:text-emerald-400",
  rejected: "bg-destructive/10 text-destructive ring-1 ring-destructive/30",
  cancelled: "bg-muted text-muted-foreground ring-1 ring-border",
};

function StatusBadge({ status }: { status: PortalLeaveRequestStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        STATUS_STYLES[status] ?? STATUS_STYLES.cancelled,
      )}
    >
      {status}
    </span>
  );
}

/** Leave-type name lookup with a readable fallback for unknown codes. */
function typeName(me: PortalMe, code: string): string {
  return me.leaveTypes.find((type) => type.code === code)?.name ?? code;
}

export function LeavePortal() {
  const [load, setLoad] = useState<LoadState>({ state: "loading" });
  const [requests, setRequests] = useState<PortalLeaveRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(true);
  const [suggestions, setSuggestions] = useState<PortalLeaveSuggestion[]>([]);

  const [leaveType, setLeaveType] = useState<string>("");
  const [startDate, setStartDate] = useState<string | null>(null);
  const [endDate, setEndDate] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [savingSuggestion, setSavingSuggestion] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const loadRequests = useCallback(async () => {
    setRequestsLoading(true);
    try {
      const result = await listMyLeaveRequests({ pageSize: 50 });
      setRequests(result.items);
    } catch {
      // The header cards still render; history degrades to an inline note.
      setRequests([]);
    } finally {
      setRequestsLoading(false);
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    try {
      const result = await getLeaveSuggestions();
      // Chips are only actionable while pending; used/dismissed are filtered
      // out client-side so a stale row never lingers on screen.
      setSuggestions(
        result.filter((suggestion) => suggestion.status === "pending"),
      );
    } catch {
      // Suggestions are optional polish — the form still works without them.
      setSuggestions([]);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoad({ state: "loading" });
    try {
      const me = await getPortalMe();
      setLoad({ state: "ready", me });
      await Promise.all([loadRequests(), loadSuggestions()]);
    } catch (error) {
      setLoad({
        state: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "Could not load your leave portal.",
      });
    }
  }, [loadRequests, loadSuggestions]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  /** Prefill the form from a suggestion — never auto-submits a request. */
  async function applySuggestion(suggestion: PortalLeaveSuggestion) {
    setSubmitError(null);
    setSubmitSuccess(false);
    setSavingSuggestion(suggestion.suggestionId);
    try {
      await markSuggestionUsed(suggestion.suggestionId);
      setLeaveType(suggestion.leaveType);
      setStartDate(suggestion.startDate);
      setEndDate(suggestion.endDate);
      setSuggestions((current) =>
        current.filter((item) => item.suggestionId !== suggestion.suggestionId),
      );
    } catch {
      setSubmitError("Could not apply the suggestion. The form was not changed.");
    } finally {
      setSavingSuggestion(null);
    }
  }

  async function dismissSuggestion(suggestion: PortalLeaveSuggestion) {
    try {
      await dismissLeaveSuggestion(suggestion.suggestionId);
      setSuggestions((current) =>
        current.filter((item) => item.suggestionId !== suggestion.suggestionId),
      );
    } catch {
      // Non-essential: leaving the chip visible is a safe fallback.
    }
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!load.state || load.state !== "ready" || !leaveType || !startDate || !endDate) {
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    if (startDate < today) {
      setSubmitError("Start date cannot be in the past.");
      return;
    }
    if (endDate < startDate) {
      setSubmitError("End date cannot be before start date.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(false);
    try {
      await submitLeaveRequest({
        leaveType,
        startDate,
        endDate,
        reason: reason.trim() || undefined,
      });
      setSubmitSuccess(true);
      setLeaveType("");
      setStartDate(null);
      setEndDate(null);
      setReason("");
      await Promise.all([loadRequests(), loadAll()]);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError ? error.message : "Could not submit the request.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (load.state === "loading") {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
        <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
        Loading your leave portal…
      </div>
    );
  }

  if (load.state === "error") {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-xl border border-border bg-card p-6 text-center">
        <h1 className="font-display text-lg font-semibold">Leave portal</h1>
        <p className="mt-2 text-sm text-muted-foreground">{load.message}</p>
      </div>
    );
  }

  const { me } = load;
  const balanceByType = new Map(me.balances.map((b) => [b.leaveType, b.balance]));
  const canSubmit = Boolean(leaveType && startDate && endDate);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          My leave
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {me.employee.firstName} {me.employee.lastName} ·{" "}
          {me.employee.employeeNumber}
        </p>
      </div>

      <section aria-labelledby="balances-heading" className="space-y-3">
        <h2 id="balances-heading" className="text-sm font-medium text-muted-foreground">
          Balances
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {me.leaveTypes.map((type) => {
            const balance = balanceByType.get(type.code);
            return (
              <div
                key={type.code}
                className="rounded-xl border border-border bg-card p-4"
              >
                <p className="text-sm font-medium">{type.name}</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums">
                  {type.isAccrual && balance !== undefined ? balance : "—"}
                  {type.isAccrual && balance !== undefined ? (
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      days
                    </span>
                  ) : null}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {suggestions.length > 0 ? (
        <section aria-labelledby="suggestions-heading" className="space-y-3">
          <h2
            id="suggestions-heading"
            className="text-sm font-medium text-muted-foreground"
          >
            Time-off suggestions
          </h2>
          <ul className="space-y-2">
            {suggestions.map((suggestion) => (
              <li
                key={suggestion.suggestionId}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div className="flex min-w-0 items-start gap-2">
                  <Sparkles
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0 text-primary"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {typeName(me, suggestion.leaveType)}
                      <span className="ml-2 font-normal tabular-nums text-muted-foreground">
                        {suggestion.days} {suggestion.days === 1 ? "day" : "days"}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(suggestion.startDate)} – {formatDate(suggestion.endDate)}
                      {suggestion.reasons[0] ? ` · ${suggestion.reasons[0]}` : ""}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={savingSuggestion === suggestion.suggestionId}
                    onClick={() => void applySuggestion(suggestion)}
                  >
                    {savingSuggestion === suggestion.suggestionId ? (
                      <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin" />
                    ) : null}
                    Fill form
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`Dismiss suggestion for ${typeName(me, suggestion.leaveType)}`}
                    disabled={savingSuggestion === suggestion.suggestionId}
                    onClick={() => void dismissSuggestion(suggestion)}
                  >
                    <X aria-hidden="true" className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            A suggestion only fills the form below — it never submits anything.
          </p>
        </section>
      ) : null}

      <section aria-labelledby="submit-heading" className="space-y-3">
        <h2 id="submit-heading" className="text-sm font-medium text-muted-foreground">
          Request time off
        </h2>
        <form
          onSubmit={onSubmit}
          className="rounded-xl border border-border bg-card p-5"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <label htmlFor="portal-leave-type" className="text-sm font-medium">
                Leave type
              </label>
              <Select value={leaveType} onValueChange={setLeaveType}>
                <SelectTrigger id="portal-leave-type" className="w-full">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {me.leaveTypes.map((type) => (
                    <SelectItem key={type.code} value={type.code}>
                      {type.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="portal-start-date" className="text-sm font-medium">
                First day
              </label>
              <DatePicker
                id="portal-start-date"
                value={startDate}
                onChange={setStartDate}
                min={new Date().toISOString().slice(0, 10)}
                lockYear
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="portal-end-date" className="text-sm font-medium">
                Last day
              </label>
              <DatePicker
                id="portal-end-date"
                value={endDate}
                onChange={setEndDate}
                min={startDate || new Date().toISOString().slice(0, 10)}
                lockYear
                invalid={Boolean(startDate && endDate && endDate < startDate)}
                required
              />
            </div>
          </div>
          <div className="mt-4 space-y-1.5">
            <label htmlFor="portal-reason" className="text-sm font-medium">
              Note <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <Textarea
              id="portal-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Anything your manager should know"
            />
          </div>
          {submitError ? (
            <p role="alert" className="mt-3 text-sm font-medium text-destructive">
              {submitError}
            </p>
          ) : null}
          {submitSuccess ? (
            <p role="status" className="mt-3 text-sm font-medium text-emerald-700 dark:text-emerald-400">
              Request submitted — it now shows as pending below.
            </p>
          ) : null}
          <div className="mt-4 flex justify-end">
            <Button type="submit" disabled={!canSubmit || submitting}>
              {submitting ? (
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
              ) : (
                <Send aria-hidden="true" className="size-4" />
              )}
              Submit request
            </Button>
          </div>
        </form>
      </section>

      <section aria-labelledby="history-heading" className="space-y-3">
        <h2 id="history-heading" className="text-sm font-medium text-muted-foreground">
          History
        </h2>
        {requestsLoading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
            Loading requests…
          </div>
        ) : requests.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card px-4 py-12 text-center">
            <CalendarDays aria-hidden="true" className="size-6 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              No requests yet — submit your first one above.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
            {requests.map((request) => (
              <li
                key={request.id}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">
                    {typeName(me, request.leaveType)}
                    <span className="ml-2 font-normal tabular-nums text-muted-foreground">
                      {request.days} {request.days === 1 ? "day" : "days"}
                    </span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(request.startDate)} – {formatDate(request.endDate)}
                    {request.reason ? ` · ${request.reason}` : ""}
                  </p>
                </div>
                <StatusBadge status={request.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
