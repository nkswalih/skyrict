#!/bin/sh
# =============================================================================
# Skyrict API Gateway - container entrypoint
#
# Renders /etc/nginx/gateway.conf.template into /etc/nginx/gateway.conf, then
# execs nginx in the foreground as PID 1 so that Container Apps' liveness
# probe and the orchestrator's SIGTERM both reach the real process.
#
# Why render at startup instead of shipping a static conf:
#
#   * The resolver address. nginx needs an explicit `resolver` to re-resolve
#     backend names when proxy_pass uses variables, and that address is only
#     known from the container's own /etc/resolv.conf. ACA's DNS differs
#     between the consumption-with-VNet environment we deploy and anything a
#     developer runs locally, so it cannot be hardcoded.
#   * The backend names. ACA short names (identity, core) work in the default
#     environment, but pinning the full internal FQDNs makes the target
#     explicit and survives an environment where short-name resolution is
#     unavailable. Both are just env vars.
#
# Every substitution is validated. A gateway that starts with a half-rendered
# config would boot "successfully" and then 502 every request; failing here
# puts the replica in CrashLoopBackOff where the orchestrator's logs say why.
# =============================================================================

set -eu

TEMPLATE="/etc/nginx/gateway.conf.template"
# Rendered into /tmp, not /etc/nginx: the image runs as non-root (uid 101) and
# /etc/nginx is root-owned read-only, so writing there fails with EACCES. /tmp is
# writable by the runtime user. The live config is per-deployment anyway - it is
# derived from the environment's DNS and backend names - so there is nothing to
# gain from persisting it.
OUTPUT="/tmp/gateway.conf"

log() { echo "[gateway-entrypoint] $*"; }
die() { echo "[gateway-entrypoint] FATAL: $*" >&2; exit 1; }

[ -f "$TEMPLATE" ] || die "template not found at $TEMPLATE"

# --- Resolver ---------------------------------------------------------------
# Take the first nameserver out of /etc/resolv.conf. Inside a container this is
# the platform resolver (ACA's internal DNS, or Docker's embedded 127.0.0.11 for
# local compose runs).
RESOLVER="${SKYRRICT_RESOLVER:-}"
if [ -z "$RESOLVER" ]; then
  RESOLVER="$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf)"
fi
[ -n "$RESOLVER" ] || die "no nameserver in /etc/resolv.conf and SKYRRICT_RESOLVER unset"
log "resolver: $RESOLVER"

# --- Backends ---------------------------------------------------------------
# Defaults match the ACA short names. The Bicep module overrides these with the
# apps' internal FQDNs so the target is explicit.
IDENTITY_BACKEND="${SKYRRICT_IDENTITY_BACKEND:-http://identity:8000}"
CORE_BACKEND="${SKYRRICT_CORE_BACKEND:-http://core:8001}"
IDENTITY_HOST="${SKYRRICT_IDENTITY_HOST:-identity}"
CORE_HOST="${SKYRRICT_CORE_HOST:-core}"

for pair in "SKYRRICT_IDENTITY_BACKEND:$IDENTITY_BACKEND" \
            "SKYRRICT_CORE_BACKEND:$CORE_BACKEND" \
            "SKYRRICT_IDENTITY_HOST:$IDENTITY_HOST" \
            "SKYRRICT_CORE_HOST:$CORE_HOST"; do
  name="${pair%%:*}"
  value="${pair#*:}"
  [ -n "$value" ] || die "$name is empty"
done

# nginx map values are literal strings, and the substitution happens on the
# template text, so a backend containing nginx's own delimiter characters would
# produce a config that parses as something other than what was asked for.
# Rejecting it here beats debugging a silently misrouted request.
for value in "$IDENTITY_BACKEND" "$CORE_BACKEND" "$IDENTITY_HOST" "$CORE_HOST"; do
  case "$value" in
    *'}'*|*';'*|*'{'*)
      die "backend/host value contains a character nginx treats as a delimiter: $value"
      ;;
  esac
done

log "identity backend: $IDENTITY_BACKEND (Host: $IDENTITY_HOST)"
log "core backend:     $CORE_BACKEND (Host: $CORE_HOST)"

# --- Runtime directories ---------------------------------------------------
# nginx creates its *_temp_path directories itself, but only one level deep, and
# only if the parent already exists. The config points them at /tmp/nginx/*,
# because the image runs as non-root and /var/cache/nginx is root-owned. Create
# the parent here, or `nginx -t` fails with ENOENT on /tmp/nginx - an error that
# says nothing about the real cause.
mkdir -p /tmp/nginx || die "could not create /tmp/nginx"

# --- Render -----------------------------------------------------------------
sed \
  -e "s|__RESOLVER__|$RESOLVER|g" \
  -e "s|__IDENTITY_BACKEND__|$IDENTITY_BACKEND|g" \
  -e "s|__IDENTITY_HOST__|$IDENTITY_HOST|g" \
  -e "s|__CORE_BACKEND__|$CORE_BACKEND|g" \
  -e "s|__CORE_HOST__|$CORE_HOST|g" \
  "$TEMPLATE" > "$OUTPUT"

# A placeholder surviving the render means a substitution was missed, and nginx
# would then treat the literal __NAME__ as a hostname.
if grep -q '__[A-Z_]*__' "$OUTPUT"; then
  die "unsubstituted placeholders remain in the rendered config:"
  grep -o '__[A-Z_]*__' "$OUTPUT" | sort -u >&2
fi

# --- Validate before taking traffic ----------------------------------------
# nginx -t is the only thing standing between a typo here and a CrashLoopBackOff
# that only shows up after the first deploy. Fail fast and loudly instead.
if ! nginx -t -c "$OUTPUT"; then
  die "rendered config failed nginx -t"
fi
log "config rendered and validated"

# --- Run --------------------------------------------------------------------
# exec so nginx replaces this shell: signals from the orchestrator (SIGTERM on
# scale-in, SIGKILL after the grace period) go to nginx itself rather than to a
# shell that would swallow them and force a kill.
log "starting nginx"
exec nginx -c "$OUTPUT" -g 'daemon off;'
