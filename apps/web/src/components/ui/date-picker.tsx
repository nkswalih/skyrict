"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type DateParts = { y: number; m: number; d: number };
type ViewMonth = { y: number; m: number };

/** Strict local-safe ISO parse — never UTC-parses "YYYY-MM-DD". */
function parseIso(iso: string): DateParts | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  return { y, m, d };
}

function toIso({ y, m, d }: DateParts): string {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function todayParts(): DateParts {
  const now = new Date();
  return { y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() };
}

/**
 * Selectable year window, computed from the system clock so it rolls
 * forward automatically: last year and the current year only. The product
 * never plans dates in the past beyond corrections or in future years, so
 * anything outside this range is unreachable through the picker.
 *
 * When `lockYear` is true, the window collapses to the current year only
 * (used by leave-request pickers where year selection is meaningless).
 */
function yearWindow(lockYear?: boolean): { minYear: number; maxYear: number } {
  const current = new Date().getFullYear();
  if (lockYear) return { minYear: current, maxYear: current };
  return { minYear: current - 1, maxYear: current };
}

/** Pin a view month inside the selectable year window. */
function clampView({ y, m }: ViewMonth, lockYear?: boolean): ViewMonth {
  const { minYear, maxYear } = yearWindow(lockYear);
  if (y < minYear) return { y: minYear, m: 1 };
  if (y > maxYear) return { y: maxYear, m: 12 };
  return { y, m };
}

function formatDisplay(iso: string): string {
  const parts = parseIso(iso);
  if (!parts) return "";
  return `${String(parts.d).padStart(2, "0")}-${String(parts.m).padStart(2, "0")}-${parts.y}`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

type Cell = { iso: string; label: number; inMonth: boolean };

/**
 * Themed date picker replacing the native browser calendar popup. The month
 * grid renders inline (sibling of the trigger button) so it stays inside the
 * nearest DismissableLayer tree — Radix Dialog sees calendar interactions as
 * "inside" and never dismisses the dialog. Position: absolute inside the
 * wrapper keeps the calendar anchored to its trigger regardless of whether
 * the wrapper lives inside a transformed DialogContent or on a scrollable
 * page. Inherits the active theme-world tokens (e.g. the ERP green) via
 * CSS custom-property cascade.
 *
 * Value contract: ISO "YYYY-MM-DD" or null; onChange emits the same.
 */
export function DatePicker({
  id,
  value,
  onChange,
  disabled,
  invalid,
  required,
  placeholder = "dd-mm-yyyy",
  className,
  min,
  lockYear,
}: {
  id?: string;
  value: string | null;
  onChange: (iso: string | null) => void;
  disabled?: boolean;
  invalid?: boolean;
  required?: boolean;
  placeholder?: string;
  className?: string;
  min?: string;
  lockYear?: boolean;
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const [view, setView] = useState<ViewMonth>(() => {
    const today = todayParts();
    return { y: today.y, m: today.m };
  });
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [monthOpen, setMonthOpen] = useState(false);
  const [yearOpen, setYearOpen] = useState(false);

  const selected = useMemo(() => parseIso(value ?? ""), [value]);

  // Measure trigger and compute dropdown position relative to the wrapper.
  // Container-relative coords work inside both a transformed DialogContent
  // (where position:fixed degrades to absolute) and on a scrollable page
  // (where absolute scrolls with the wrapper).
  const CALENDAR_HEIGHT = 320; // px — 5-row month grid + header + footer
  const CALENDAR_WIDTH = 288; // w-72 = 18rem = 288px

  function computePosition() {
    const el = triggerRef.current;
    const wrapper = wrapperRef.current;
    if (!el || !wrapper) return;
    const triggerRect = el.getBoundingClientRect();
    const wrapperRect = wrapper.getBoundingClientRect();

    // Vertical: flip above if not enough room below inside the wrapper.
    const spaceBelow = triggerRect.bottom - wrapperRect.bottom;
    let top: number;
    if (spaceBelow < CALENDAR_HEIGHT + 8) {
      top = triggerRect.top - wrapperRect.top - CALENDAR_HEIGHT - 4;
    } else {
      top = triggerRect.bottom - wrapperRect.top + 4;
    }
    top = Math.max(0, top);

    // Horizontal: left-align with trigger, clamp so right edge stays inside wrapper.
    let left = triggerRect.left - wrapperRect.left;
    if (left + CALENDAR_WIDTH > wrapperRect.width) {
      left = wrapperRect.width - CALENDAR_WIDTH;
    }
    left = Math.max(0, left);

    setDropdownPos({ top, left });
  }

  // Measure on open and re-measure on scroll/resize while open.
  useLayoutEffect(() => {
    if (!open) return;
    computePosition();
    const onReposition = () => computePosition();
    window.addEventListener("scroll", onReposition, true);
    window.addEventListener("resize", onReposition);
    return () => {
      window.removeEventListener("scroll", onReposition, true);
      window.removeEventListener("resize", onReposition);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function openPanel() {
    const base = selected ?? todayParts();
    setView(clampView({ y: base.y, m: base.m }, lockYear));
    setHighlighted(toIso(base));
    setOpen(true);
  }

  // Escape must never reach the Dialog's dismissable layer (it listens on
  // `document` in the capture phase), so swallow it here first and close
  // only this popup.
  useEffect(() => {
    function handleCapture(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      const wrapper = wrapperRef.current;
      if (!wrapper || !event.target) return;
      if (!wrapper.contains(event.target as Node)) return;
      event.stopImmediatePropagation();
      setOpen(false);
    }
    document.addEventListener("keydown", handleCapture, true);
    return () => document.removeEventListener("keydown", handleCapture, true);
  }, []);

  // Click-outside closes the popup. The calendar renders inline inside the
  // DismissableLayer tree, so Radix Dialog won't dismiss on calendar clicks.
  // Match the calendar's role="dialog", its month/year dropdowns, and their
  // items to keep them interactive.
  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as HTMLElement;
      if (target.closest('[role="dialog"][aria-label="Choose date"]')) return;
      if (target.closest("[role=\"option\"]")) return;
      if (target.closest("[role=\"listbox\"]")) return;
      const wrapper = wrapperRef.current;
      if (wrapper && wrapper.contains(target)) return;
      setOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown, true);
    return () => document.removeEventListener("pointerdown", handlePointerDown, true);
  }, [open]);

  const cells = useMemo<Cell[]>(() => {
    const lead = new Date(view.y, view.m - 1, 1).getDay();
    const daysInMonth = new Date(view.y, view.m, 0).getDate();
    const out: Cell[] = [];
    const pushCell = (date: Date, inMonth: boolean) =>
      out.push({
        iso: toIso({
          y: date.getFullYear(),
          m: date.getMonth() + 1,
          d: date.getDate(),
        }),
        label: date.getDate(),
        inMonth,
      });
    // Leading days from the previous month (Date rollover handles months).
    for (let i = lead; i > 0; i--) pushCell(new Date(view.y, view.m - 1, 1 - i), false);
    for (let d = 1; d <= daysInMonth; d++) pushCell(new Date(view.y, view.m - 1, d), true);
    // Trailing days to complete the final week (minimum five rows).
    let nextOffset = 1;
    while (out.length < 35 || out.length % 7 !== 0) {
      pushCell(new Date(view.y, view.m - 1, daysInMonth + nextOffset), false);
      nextOffset++;
    }
    return out;
  }, [view]);

  /** Shift the highlighted day, rolling the visible month when needed. */
  const moveHighlight = useCallback(
    (days: number) => {
      const base = parseIso(highlighted ?? "") ?? todayParts();
      const shifted = new Date(base.y, base.m - 1, base.d + days);
      const next: DateParts = {
        y: shifted.getFullYear(),
        m: shifted.getMonth() + 1,
        d: shifted.getDate(),
      };
      setHighlighted(toIso(next));
      if (next.m !== view.m || next.y !== view.y) setView(clampView({ y: next.y, m: next.m }, lockYear));
    },
    [highlighted, view, lockYear],
  );
  function commit(iso: string | null) {
    onChange(iso);
    setOpen(false);
  }

  function shiftView(months: number) {
    setView((current) => {
      // Day 1 keeps the month arithmetic unambiguous across lengths.
      const shifted = new Date(current.y, current.m - 1 + months, 1);
      return clampView({ y: shifted.getFullYear(), m: shifted.getMonth() + 1 }, lockYear);
    });
  }

  /** Last year and the current year, from the live system clock. */
  const { minYear, maxYear } = useMemo(() => yearWindow(lockYear), [lockYear]);
  const yearOptions = useMemo(() => {
    const years: number[] = [];
    for (let y = minYear; y <= maxYear; y++) years.push(y);
    return years;
  }, [minYear, maxYear]);

  const atStart =
    view.y === minYear && view.m === 1;
  const atEnd = view.y === maxYear && view.m === 12;

  function handleKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    // Let the month/year dropdown buttons handle their own keyboard interaction.
    if ((event.target as HTMLElement).closest('[role="option"]')) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) openPanel();
      else moveHighlight(7);
    } else if (event.key === "ArrowUp" && open) {
      event.preventDefault();
      moveHighlight(-7);
    } else if (event.key === "ArrowRight" && open) {
      event.preventDefault();
      moveHighlight(1);
    } else if (event.key === "ArrowLeft" && open) {
      event.preventDefault();
      moveHighlight(-1);
    } else if (event.key === "Enter") {
      // Never let Enter submit the surrounding form from this widget.
      event.preventDefault();
      if (open && highlighted) commit(highlighted);
    } else if (event.key === "Tab" && open) {
      setOpen(false);
    }
  }

  const displayValue = value ? formatDisplay(value) : "";

  // aria-invalid/aria-required are global ARIA attributes; keeping them off
  // the JSX tag also sidesteps the a11y plugin's outdated role table.
  const validationAria = {
    "aria-invalid": invalid || undefined,
    "aria-required": required || undefined,
  };

  /** Custom inline dropdown that renders inside the calendar (no portal needed). */
  function renderDropdown(opts: {
    open: boolean;
    onToggle: () => void;
    value: string;
    ariaLabel: string;
    className?: string;
    items: { key: string; label: string }[];
    onSelect: (value: string) => void;
  }) {
    return (
      <div className="relative">
        <button
          type="button"
          aria-label={opts.ariaLabel}
          aria-expanded={opts.open}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            opts.onToggle();
          }}
          className={cn(
            "flex h-7 items-center justify-between gap-1 rounded-md border border-input bg-transparent px-1.5 text-sm outline-none",
            opts.className,
          )}
        >
          <span className="truncate">
            {opts.items.find((i) => i.key === opts.value)?.label ?? opts.value}
          </span>
          <ChevronDown className="size-3 shrink-0 opacity-50" />
        </button>
        {opts.open && (
          <div
            role="listbox"
            aria-label={opts.ariaLabel}
            onMouseDown={(event) => event.stopPropagation()}
            className="absolute top-full left-0 z-[10000] mt-0.5 max-h-52 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-md"
          >
            {opts.items.map((item) => (
              <div
                key={item.key}
                role="option"
                aria-selected={item.key === opts.value}
                onClick={(event) => {
                  event.stopPropagation();
                  opts.onSelect(item.key);
                  opts.onToggle();
                }}
                className={cn(
                  "cursor-pointer px-2 py-1 text-sm outline-none hover:bg-accent",
                  item.key === opts.value && "bg-accent font-medium",
                )}
              >
                {item.label}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  const calendarDropdown = open ? (
    <div
      role="dialog"
      aria-label="Choose date"
      className="absolute z-[9999] w-72 rounded-lg border border-border bg-popover p-2 text-popover-foreground shadow-md outline-none"
      style={{ top: dropdownPos.top, left: dropdownPos.left }}
    >
      <div className="mb-1 flex items-center gap-1">
        <button
          type="button"
          aria-label="Previous month"
          disabled={atStart}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => shiftView(-1)}
          className="rounded-md p-1 text-popover-foreground transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
        >
          <ChevronLeft aria-hidden="true" className="size-4" />
        </button>
        {renderDropdown({
          open: monthOpen,
          onToggle: () => { setMonthOpen((v) => !v); setYearOpen(false); },
          value: String(view.m),
          ariaLabel: "Month",
          className: "min-w-0 flex-1",
          items: MONTH_NAMES.map((name, index) => ({ key: String(index + 1), label: name })),
          onSelect: (month) => setView((current) => ({ ...current, m: Number(month) })),
        })}
        {!lockYear ? (
          renderDropdown({
            open: yearOpen,
            onToggle: () => { setYearOpen((v) => !v); setMonthOpen(false); },
            value: String(view.y),
            ariaLabel: "Year",
            className: "w-[5.75rem] shrink-0",
            items: yearOptions.map((year) => ({ key: String(year), label: String(year) })),
            onSelect: (year) => setView((current) => ({ ...current, y: Number(year) })),
          })
        ) : (
          <span className="h-7 w-[5.75rem] shrink-0 text-sm font-medium text-popover-foreground">
            {view.y}
          </span>
        )}
        <button
          type="button"
          aria-label="Next month"
          disabled={atEnd}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => shiftView(1)}
          className="rounded-md p-1 text-popover-foreground transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-40"
        >
          <ChevronRight aria-hidden="true" className="size-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-0.5" role="grid">
        {WEEKDAYS.map((weekday) => (
          <span
            key={weekday}
            aria-hidden="true"
            className="flex size-8 items-center justify-center text-xs font-medium text-muted-foreground"
          >
            {weekday}
          </span>
        ))}
        {cells.map((cell) => {
          const isSelected = cell.iso === value;
          const isHighlighted = cell.iso === highlighted;
          const isToday = cell.iso === toIso(todayParts());
          const isPast = Boolean(min && cell.iso < min);
          return (
            <button
              key={cell.iso}
              type="button"
              role="gridcell"
              disabled={isPast || undefined}
              aria-disabled={isPast || undefined}
              aria-selected={isSelected || undefined}
              aria-label={cell.iso}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => { if (!isPast) commit(cell.iso); }}
              className={cn(
                "flex size-8 items-center justify-center rounded-md text-sm transition-colors",
                cell.inMonth ? "text-popover-foreground" : "text-muted-foreground/50",
                isPast && "cursor-not-allowed text-muted-foreground/30",
                isHighlighted && !isSelected && !isPast && "bg-accent",
                !isHighlighted && !isSelected && !isPast && "hover:bg-accent",
                isSelected && "bg-primary font-medium text-primary-foreground",
                isToday && !isSelected && "font-semibold text-primary ring-1 ring-inset ring-primary/40",
              )}
            >
              {cell.label}
            </button>
          );
        })}
      </div>
      <div className="mt-1 flex items-center justify-between border-t border-border pt-1">
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => commit(toIso(todayParts()))}
          className="rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent"
        >
          Today
        </button>
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => commit(null)}
          className="rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent"
        >
          Clear
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div ref={wrapperRef} className={cn("relative", className)}>
      <button
        type="button"
        ref={triggerRef}
        id={id}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        {...validationAria}
        onClick={() => (open ? setOpen(false) : openPanel())}
        onKeyDown={handleKeyDown}
        className={cn(
          "flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-2.5 py-1 text-left text-base transition-colors outline-none md:text-sm dark:bg-input/30",
          "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          "aria-invalid:border-destructive",
          "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        <span className={cn("min-w-0 truncate", !displayValue && "text-muted-foreground")}>
          {displayValue || placeholder}
        </span>
        <Calendar aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
      </button>
      {calendarDropdown}
    </div>
  );
}
