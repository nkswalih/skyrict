/**
 * The invite page's reading of identity's RFC 7807 problem types.
 *
 * The behaviour that matters here is not the happy path, it is that the page
 * must not silently report the wrong invite failure. Before this rule was
 * extracted it compared the whole `type` URI against a base the web app
 * hardcoded itself, so the two sides could disagree about the domain and the
 * only symptom would be a user being told their expired invite link was
 * "invalid" - with a correct-looking page and no error anywhere.
 */

import { describe, expect, it } from "vitest";

import { classifyInviteProblem } from "./invitation-problem-types";

const LIVE = "https://api.skyrict.in/problems";

describe("classifyInviteProblem", () => {
  it("recognises an expired invite", () => {
    expect(classifyInviteProblem(`${LIVE}/invitation-expired`)).toBe("expired");
  });

  it("recognises an already-used invite", () => {
    expect(classifyInviteProblem(`${LIVE}/invitation-already-used`)).toBe(
      "alreadyUsed",
    );
  });

  it("does not depend on which host publishes the contract", () => {
    // This is the regression the extraction exists for. The public domain has
    // moved .com -> .io -> .in; the page must not care, and must not need a
    // code change when it moves again.
    for (const base of [
      "https://api.skyrict.com/problems",
      "https://api.skyrict.io/problems",
      "https://api.skyrict.in/problems",
      "http://identity:8000/api/v1/problems",
    ]) {
      expect(classifyInviteProblem(`${base}/invitation-expired`)).toBe("expired");
    }
  });

  it("returns null for a problem it does not own", () => {
    // The caller falls back to its own "invalid" outcome. Guessing here would
    // show a user the wrong remediation for a problem we do not define.
    expect(classifyInviteProblem(`${LIVE}/validation-error`)).toBeNull();
    expect(classifyInviteProblem(`${LIVE}/user-not-found`)).toBeNull();
  });

  it("returns null when there is no type at all", () => {
    // A non-problem failure (a proxy 502, an empty body) must not be
    // classified as an invite problem.
    expect(classifyInviteProblem(undefined)).toBeNull();
    expect(classifyInviteProblem(null)).toBeNull();
    expect(classifyInviteProblem("")).toBeNull();
  });

  it("returns null for a non-string type", () => {
    // `type` arrives from an untyped JSON body, so it is not guaranteed to be
    // a string. Calling .endsWith on it would throw and turn a bad invite into
    // a 500.
    expect(classifyInviteProblem(404)).toBeNull();
    expect(classifyInviteProblem({ type: "invitation-expired" })).toBeNull();
    expect(classifyInviteProblem(["invitation-expired"])).toBeNull();
  });

  it("does not match a longer slug that merely shares a prefix", () => {
    // The slug is a whole path segment. A different problem that happens to
    // start with the same words is a different problem.
    expect(classifyInviteProblem(`${LIVE}/invitation-expired-v2`)).toBeNull();
    expect(classifyInviteProblem(`${LIVE}/invitation-already-used-now`)).toBeNull();
  });

  it("does not match a bare slug fragment without its separator", () => {
    expect(classifyInviteProblem("invitation-expired")).toBeNull();
  });
});
