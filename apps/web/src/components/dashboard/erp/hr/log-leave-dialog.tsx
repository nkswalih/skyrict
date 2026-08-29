"use client";

import { useEffect, useMemo, useState } from "react";
import { LoaderCircle, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DatePicker } from "@/components/ui/date-picker";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  SearchableSelect,
  type SearchableSelectOption,
} from "@/components/dashboard/shared/searchable-select";
import {
  byEmployeeName,
  createLeaveRequest,
  employeeName,
  listEmployeeSuggestions,
  type Employee,
  type HrLeaveSuggestion,
} from "@/lib/api/hr-api";
import { ApiError } from "@/lib/api/http";
import { formatDate } from "@/lib/format";

const LEAVE_TYPES = [
  { value: "casual", label: "Casual" },
  { value: "sick", label: "Sick" },
  { value: "unpaid", label: "Unpaid" },
] as const;

type FormState = {
  employeeId: string;
  leaveType: string;
  startDate: string;
  endDate: string;
  reason: string;
};

const EMPTY_FORM: FormState = {
  employeeId: "",
  leaveType: "",
  startDate: "",
  endDate: "",
  reason: "",
};

function typeCallout(leaveType: string): string | null {
  if (leaveType === "unpaid") {
    return "This unpaid leave will reduce the employee\u2019s pay for the affected period.";
  }
  if (leaveType === "casual" || leaveType === "sick") {
    return "This leave will be deducted from the employee\u2019s balance upon approval.";
  }
  return null;
}

interface LogLeaveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employees: Employee[];
  prefillEmployeeId?: string | null;
  onCreated?: () => void;
}

export function LogLeaveDialog({
  open,
  onOpenChange,
  employees,
  prefillEmployeeId,
  onCreated,
}: LogLeaveDialogProps) {
  const [form, setForm] = useState<FormState>(() => ({
    ...EMPTY_FORM,
    employeeId: prefillEmployeeId ?? "",
  }));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const employeeOptions = useMemo<SearchableSelectOption[]>(
    () =>
      [...employees]
        .sort(byEmployeeName)
        .map((emp) => ({
          value: emp.id,
          label: employeeName(emp),
          keywords: emp.employeeNumber,
        })),
    [employees],
  );
  const leaveTypeOptions = useMemo<SearchableSelectOption[]>(
    () => LEAVE_TYPES.map((lt) => ({ value: lt.value, label: lt.label })),
    [],
  );

  const [suggestions, setSuggestions] = useState<HrLeaveSuggestion[]>([]);

  useEffect(() => {
    const employeeId = form.employeeId;
    if (!employeeId) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    listEmployeeSuggestions(employeeId)
      .then((rows) => {
        if (!cancelled) setSuggestions(rows);
      })
      .catch(() => {
        // Suggestions are optional polish: missing `erp.hr.ai.individual`
        // (403) or any other failure just leaves the dialog suggestion-free.
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [form.employeeId]);

  function prefillSuggestion(suggestion: HrLeaveSuggestion) {
    setError(null);
    const supported = LEAVE_TYPES.some(
      (option) => option.value === suggestion.leaveType,
    );
    if (supported) updateField("leaveType", suggestion.leaveType);
    updateField("startDate", suggestion.startDate);
    updateField("endDate", suggestion.endDate);
  }

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleClose(nextOpen: boolean) {
    if (saving) return;
    if (!nextOpen) {
      setForm({ ...EMPTY_FORM, employeeId: prefillEmployeeId ?? "" });
      setError(null);
    }
    onOpenChange(nextOpen);
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;

    if (!form.employeeId) {
      setError("Employee is required.");
      return;
    }
    if (!form.leaveType) {
      setError("Leave type is required.");
      return;
    }
    if (!form.startDate || !form.endDate) {
      setError("Start and end dates are required.");
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    if (form.startDate < today) {
      setError("Start date cannot be in the past.");
      return;
    }
    if (form.endDate < form.startDate) {
      setError("End date cannot be before start date.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createLeaveRequest({
        employeeId: form.employeeId,
        leaveType: form.leaveType,
        startDate: form.startDate,
        endDate: form.endDate,
        reason: form.reason.trim() || undefined,
      });
      handleClose(false);
      onCreated?.();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not create leave request.",
      );
    } finally {
      setSaving(false);
    }
  }

  const callout = typeCallout(form.leaveType);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={(e) => void onSubmit(e)}>
          <DialogHeader>
            <DialogTitle>Log leave</DialogTitle>
            <DialogDescription>
              Create a leave request on behalf of an employee.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="log-employee">Employee</Label>
              <SearchableSelect
                id="log-employee"
                options={employeeOptions}
                value={form.employeeId || null}
                onValueChange={(value) => updateField("employeeId", value)}
                disabled={!!prefillEmployeeId}
                placeholder="Select employee"
              />
            </div>

            {suggestions.length > 0 ? (
              <div className="space-y-2">
                <Label>Suggestion chips</Label>
                <ul className="space-y-2">
                  {suggestions.map((suggestion) => (
                    <li
                      key={suggestion.suggestionId}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/40 px-3 py-2"
                    >
                      <div className="flex min-w-0 items-start gap-2">
                        <Sparkles
                          aria-hidden="true"
                          className="mt-0.5 size-3.5 shrink-0 text-primary"
                        />
                        <div className="min-w-0">
                          <p className="text-xs font-medium">
                            {suggestion.leaveType}
                            <span className="ml-1.5 font-normal tabular-nums text-muted-foreground">
                              {suggestion.days} {suggestion.days === 1 ? "day" : "days"}
                            </span>
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatDate(suggestion.startDate)} –{" "}
                            {formatDate(suggestion.endDate)}
                            {suggestion.reasons[0]
                              ? ` · ${suggestion.reasons[0]}`
                              : ""}
                          </p>
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => prefillSuggestion(suggestion)}
                      >
                        Fill form
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="log-type">Leave type</Label>
              <SearchableSelect
                id="log-type"
                options={leaveTypeOptions}
                value={form.leaveType || null}
                onValueChange={(value) => updateField("leaveType", value)}
                placeholder="Select type"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="log-start">Start date</Label>
                <DatePicker
                  id="log-start"
                  value={form.startDate || null}
                  onChange={(iso) => updateField("startDate", iso ?? "")}
                  min={new Date().toISOString().slice(0, 10)}
                  lockYear
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="log-end">End date</Label>
                <DatePicker
                  id="log-end"
                  value={form.endDate || null}
                  onChange={(iso) => updateField("endDate", iso ?? "")}
                  min={form.startDate || new Date().toISOString().slice(0, 10)}
                  lockYear
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="log-reason">Reason (optional)</Label>
              <Input
                id="log-reason"
                value={form.reason}
                onChange={(e) => updateField("reason", e.target.value)}
                placeholder="e.g. Medical appointment"
                maxLength={500}
              />
            </div>

            {callout ? (
              <p className="rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                {callout}
              </p>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className="mb-2 text-sm font-medium text-destructive">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? (
                <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
              ) : null}
              Create request
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
