# =============================================================================
# Skyrict API Gateway - nginx image
#
# Serves the single public API origin (api.skyrict.in) in front of identity and
# core. Azure Container Apps ingress is host-based and cannot route on path, so
# the /api/v1/* -> identity|core split has to be done by a reverse proxy.
#
# ai-agent is deliberately absent. It is not in the public route map: core calls
# it internally. Exposing it here would put a second, unmediated entry point in
# front of the agent runtime.
#
# Build (from the repo root):
#   docker build -f infra/docker/gateway/Dockerfile -t skyrict-gateway .
# =============================================================================

FROM nginx:1.27-alpine

# nginx:alpine's stock entrypoint writes /etc/nginx/conf.d and templates
# /etc/nginx/templates. Neither is used - this image runs one config file
# rendered by our own entrypoint - and that script's behaviour differs between
# nginx versions, so remove it rather than depend on it.
RUN rm -f /etc/nginx/conf.d/default.conf /etc/nginx/docker-entrypoint.sh

# Template plus the entrypoint that renders it. The template keeps its
# .template name so a stray `nginx -t /etc/nginx/gateway.conf` cannot mistake it
# for a live config.
COPY infra/nginx/gateway.conf.template /etc/nginx/gateway.conf.template
COPY infra/docker/gateway/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Non-root. Port 8080 rather than 80 because binding a privileged port as a
# non-root user is not permitted; ACA ingress reaches whichever port the app
# config declares, so the port is a deployment detail, not a contract.
# /var/log/nginx/{access,error}.log are symlinks to /dev/stdout and /dev/stderr
# in this base image, so log output still lands in `az containerapp logs` and the
# non-root user never needs write access to the log directory.
USER nginx

EXPOSE 8080

# Liveness only. /healthz does not touch the backends on purpose - a backend
# rollout must not take the gateway's own liveness down with it. Backend
# reachability is /readyz, which is what the Bicep readiness probe uses.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]

