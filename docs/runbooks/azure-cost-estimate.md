# Azure cost estimate: trial month vs $0/month steady state (SKY-114)

The beta environment is designed to use only Azure resources that are
**included in the Azure free account** (12-month popular services +
always-free services). The table below is the planning estimate for the
`skyrict-beta` launch with the default parameters; all figures are list
prices in USD, **before** the free-account discounts.

## Trial month (month 1, managed resources active)

| Resource | Configuration | List $/month | Free account |
| --- | --- | --- | --- |
| Container Apps Environment (Consumption) | scale-to-zero, max 2 nodes | ~$5–15 at idle traffic | 1,800,000 vCPU-s + 3,600,000 GiB-s free/mo |
| PostgreSQL Flexible Server | B1ms, 32 GB, 7-day backup | ~$25 (backup storage extra) | 750 compute hrs/**32 GB** free/mo (always free) |
| Azure Cache for Redis | Standard C0 (250 MB) | ~$15 | one 12-month free |
| Azure Container Registry | Standard | ~$0.17 | one 12-month free |
| Key Vault | Standard | ~$0.03 per 10k ops (≈ $0) | 1M operations free/mo |
| Log Analytics | 30-day retention, minimal ingestion | ~$2–5 (ingestion-based) | 5 GB free/mo |
| VNet / NSG / private endpoints / private DNS | usage-based, negligible | ~$1–3 | covered |
| **Subtotal (list)** | | **~$48–63** | **free-account offset: ~$0** |

With the free account offsets the **effective month-1 cost is $0** as long as
traffic stays well below the free quotas (the budget alerts at 50/80/90% of
$10 catch any overflow).

## Steady state (months 2–12, designed to be $0)

One configuration-only change plus parameter swap (documented in
`azure-iac.md` §10):

1. **Upgrade the free trial to PAYG within 30 days** so the 12-month free
   services keep applying into months 2–12.
2. **Swap Redis → Upstash Serverless Redis** (free tier): set the
   `AZURE_REDIS_URL_OVERRIDE` secret and deploy with `deployManagedRedis=false`
   — the Azure Redis resource and its private endpoint/vnet cost disappear.
3. **ACR → Basic SKU** (`registrySku=Basic`, ~$0.15/mo list, still covered).
4. **Postgres stays B1ms** (always-free 750 h + 32 GB) — the only always-free
   SQL option that matches the CI `postgres:16` image.
5. **Container Apps stay at `minReplicas: 0`** — zero traffic = zero
   billable compute; the 1.8M vCPU-s monthly quota covers heavy beta use.

| Resource | Configuration | List $/month (month 2+) | Effective |
| --- | --- | --- | --- |
| Container Apps (Consumption) | scale-to-zero | ~$5–15 | free quota |
| PostgreSQL Flexible Server | B1ms 32 GB | ~$25 | **always-free** |
| ACR | Basic | ~$0.15 | 12-month free |
| Key Vault | Standard | ~$0 | 1M free ops |
| Log Analytics | 30-day retention | ~$2–5 | 5 GB free |
| Upstash Redis | free tier | $0 (external) | $0 |
| **Total list** | | **~$32–45** | **effective $0** |

## Worst case / tripwires

- Traffic spam that keeps replicas at max: Consumption bill grows ~$0.000024
  / vCPU-s + $0.0000125 / GiB-s; at the 2-replica cap this stays
  < $10/mo — budget alerts fire first.
- Log ingestion above 5 GB: ~$2.9/GB; the 30-day retention cap bounds
  stored volume.
- Postgres backups: B1ms default geo-redundant backup storage has a small
  charge; if it ever matters, `backupRetentionDays` is parameterized (7
  default, min 7) — kept at the free 32 GB disk so backups are nominal.

## Year 2+

Post-trial, options with the same IaC: keep B1ms always-free indefinitely,
or scale up via parameters (`postgresSku`, `maxReplicas`, `containerCpu/Memory`)
without template changes. The cost runbook section of `azure-iac.md` §10
documents every knob.

## Assumptions

- Region `westus` (set in `beta.parameters.json`). Prices vary slightly by region.
- Beta traffic is bursty dev/demo traffic, far below free quotas.
- Budget alerts (`budgetAmount=10`, thresholds 50/80/90%) are the operational
  guard; see `azure-iac.md` §6.