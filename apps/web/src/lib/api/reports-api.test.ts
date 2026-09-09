import { describe, expect, it } from "vitest";

import { toReportSlug } from "@/lib/api/reports-api";

describe("toReportSlug", () => {
  it("lowercases and joins words with dashes", () => {
    expect(toReportSlug("AR Aging by Bucket")).toBe("ar-aging-by-bucket");
  });

  it("collapses runs of non-alphanumeric characters to a single dash", () => {
    expect(toReportSlug("Sales Orders — Q3 '26!!")).toBe("sales-orders-q3-26");
  });

  it("strips leading and trailing dashes", () => {
    expect(toReportSlug("  - Headcount by Department - ")).toBe("headcount-by-department");
  });

  it("caps at 64 chars without trailing dashes", () => {
    const slug = toReportSlug("A".repeat(80));
    expect(slug.length).toBeLessThanOrEqual(64);
    expect(slug).not.toMatch(/-$/);
  });

  it("falls back for a title with no usable characters", () => {
    expect(toReportSlug("!!!")).toBe("report");
  });
});