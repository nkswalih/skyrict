# ADR-0010: One CAPTCHA per sign-up flow, continued by a flow proof

## Status

Accepted

## Date

2026-10-03

## Context

Self-service sign-up gated every step that mattered behind its own Turnstile
check. `/auth/signup/start` verified a token server-side and returned
`{"status": "ok"}` — nothing the next step could spend. `/auth/signup/send-code`
therefore demanded a second, independently solved token, and the web app
rendered an inline widget on step 2 to produce it.

The intent was sound. `/signup/start` is the wizard's front door, but
`/signup/send-code` is the endpoint that actually spends relay quota, and
gating only the entry point would have left any caller free to mint OTPs for
arbitrary addresses.

The implementation was not. A Turnstile token is single-use with a roughly
five-minute TTL, so a user who solved one challenge at step 1 was required to
solve another within seconds of arriving at step 2. Solving twice in that window
is close to the canonical automation pattern, which means the second solve was
*more* likely to be scored as a bot than the first. The gate meant to protect
the flow was a substantial part of what broke it: beta sign-up returned "Unable
to verify you are not a robot" on a request the user had already been asked to
prove, on step 2 of a seven-step wizard.

It also protected nothing that the first solve did not. Between the two, the
user was asked for exactly the same evidence seconds apart.

## Decision

**One challenge per flow, then a proof.** The challenge stays where it earns
its keep — at the entry to the wizard. Everything after it spends a proof.

`/auth/signup/start` verifies Turnstile as before, then mints a `flowToken`
bound to the address it was solved for, with a TTL of
`SIGNUP_FLOW_TTL_SECONDS` (600s) and a budget of `SIGNUP_FLOW_MAX_SENDS` (3)
sends. `/auth/signup/send-code` no longer accepts a Turnstile token; it requires
the proof.

Three properties do the work that the second challenge used to do:

1. **The proof is bound to one address.** This is what preserves the limit a
   per-send challenge provided. While every send demanded its own challenge,
   solving one was worth exactly one address. A proof that is not bound would
   turn one solve into mail for anyone.
2. **The proof has a send budget inside a short TTL.** One solve can produce at
   most three emails to one address, within ten minutes. Consuming a send
   `INCR`s a counter whose TTL is deliberately never refreshed, so a caller
   that keeps sending cannot hold the proof open indefinitely.
3. **The budget is charged only when mail actually goes out.** A resend blocked
   by the cooldown still returns 200 with a countdown, and must not cost the
   user one of their three real codes.

`/signup/send-code` still checks the gate *before* the cooldown. A caller with
no valid proof gets 422, not a 200 that reads as a working send and hides the
fact that nothing was verified.

### Deliberately not bound to client IP

The proof is bound to the address, not to the network it was solved from. It
lives about ten seconds in practice. Pinning it to an IP would break real
signups whenever a mobile client changed network mid-flow, which is a far more
likely and more costly failure than the replay its own budget already bounds.

### Where this sits against the standards

Mainstream auth does not challenge per step. Auth0, Clerk, Supabase and Firebase
run a silent risk score over the flow, or a single challenge at entry followed
by a signed continuation; rate limits and email verification carry the
anti-abuse load. NIST SP 800-63B binds an authentication challenge to a
*session*, not to each individual request. The previous design re-challenged a
user mid-flow for a step they had already cleared.

## Consequences

- Sign-up costs one CAPTCHA solve instead of two, and cannot fail on a second
  solve that the first already covered.
- `POST /auth/signup/send-code` changes shape: `turnstileToken` is replaced by
  `flowToken`. This is a breaking API change. The service is pre-GA, so it is
  taken in one step rather than behind a compatibility window.
- The web app holds the proof in `sessionStorage`, never the URL. It authorises
  sending mail to an address, so it must stay out of browser history, `Referer`
  headers and access logs.
- A user who abandons the wizard for longer than the TTL must restart from step
  1. The verify step detects this and says so plainly instead of firing a
  request the backend will refuse.
- Solving one challenge is now worth three emails rather than one. That trade is
  deliberate: three emails to a single address, inside a ten-minute window,
  behind per-email and per-IP rate limits, is a materially smaller abuse surface
  than a solve-per-send requirement that users fail to satisfy.

## Alternatives rejected

**Drop CAPTCHA entirely and rely on rate limits alone** (option B). Simpler,
and what many products do. Weaker against high-volume scripted sign-up at the
wizard's entry, which is exactly where a challenge buys the most. Rejected.

**Keep both challenges.** Zero code change, and it keeps working. It asks the
user for the same evidence twice in a window where the second answer is
increasingly likely to be judged as automation. Rejected as a net loss for the
user and for reliability.

**Stateless signed JWT proof.** Avoids a Redis read on verification. We already
hit Redis for the resend cooldown, so there is no read saved, and a JWT cannot
be spent from a budget or revoked. The Redis-backed proof is bounded and
revocable.
