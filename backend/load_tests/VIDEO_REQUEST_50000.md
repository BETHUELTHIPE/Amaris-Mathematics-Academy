# Target: 50,000 simultaneous student video submissions

The acceptance target is **50,000**, alongside the existing 100,001-student
database fixture. Status: **NOT RUN / NOT VERIFIED** against Amaris. The small
16-thread Django check remains a CI regression test. It is not the capacity
target. Never change it to 50,000 native database threads on one CI runner.

`video_request_burst.mjs` defaults to 50,000 distinct students, each making one
multipart video checkout POST at a shared wall-clock release time. This is a
synchronized submission burst, not a rate of 50,000 requests spread over a day.
The response must be an unpaid, signed, server-priced sandbox checkout for
that exact student. The generator never follows the returned payment URL.

## Prerequisites

- Restore isolated staging. The latest connected inspection found staging and
  production suspended for billing. No services or plans were changed.
- Verify the deployed Git SHA, isolated PostgreSQL/storage, PayFast sandbox
  configuration, disabled outbound email/WhatsApp, and no production data.
  The environment assertions below are operator attestations, not remote proof.
- Prepare **50,000 distinct synthetic verified accounts** and valid short-lived
  access tokens on this isolated target. A shared token does not represent
  distinct students. Do not change authentication or throttle rules to force a
  pass. No auth accounts, real student records or live payments are created by
  the load generator itself; requests may create synthetic student profiles
  through the normal authenticated application path.
- Use monitored dedicated generators with synchronized clocks, sufficient file
  descriptors, memory, CPU, ports and bandwidth. Split the 50,000 cohort across
  machines using k6 execution segments. A regular GitHub runner is not approved
  evidence for the full load. New paid resources require separate authorization.
- Run progressively (100, 500, 1,000, 5,000, 10,000, 25,000, 50,000); stop after
  failures. Each stage needs its own run ID, manifest of exactly that many users
  and a later common release time. Reconcile all created pending requests and
  remove only that run's synthetic accounts/files under the retention policy.

## Private manifest

Keep this file outside the repository and artifacts, with restrictive access:

```json
{"students":[{"student_id":"<synthetic account UUID>","access_token":"<short-lived test token>"}]}
```

Supply the same ordered manifest to every generator. Exactly 50,000 entries,
unique case-insensitive UUIDs and unique tokens are required for the final stage.
The manifest is loaded once per k6 process via SharedArray. Do not run with HTTP
debug logging, which could disclose bearer tokens. Use no real student identities.

## Configure each generator

Run from `backend/`. Inject these values through the generator's secure runtime
environment. Use the actual isolated target and its exact deployed revision:

```bash
export LOADTEST_ENVIRONMENT=capacity
export LOADTEST_TARGET_URL=https://YOUR-ISOLATED-CAPACITY-HOST
export LOADTEST_ALLOWED_HOSTS=YOUR-ISOLATED-CAPACITY-HOST
export PAYFAST_MODE=sandbox
export VIDEO_LOAD_ISOLATION_CONFIRMED=true
export VIDEO_LOAD_USERS=50000
export VIDEO_LOAD_STUDENTS_FILE=/secure/isolated-students.json
export VIDEO_LOAD_DEPLOYED_SHA=EXACT_40_CHARACTER_DEPLOYED_GIT_SHA
export VIDEO_LOAD_RUN_ID=video50k-01
export VIDEO_LOAD_RELEASE_AT_MS=COMMON_FUTURE_UTC_EPOCH_MILLISECONDS
```

Choose one release time 30 seconds to 25 minutes ahead of generator startup,
with ample time for all VUs to initialize. Late starts fail the dispatch gate.
Every generator must use identical run ID, revision, release time and options.
The checked-in PDF is 329 bytes: this measures small supporting-document
submissions. Large uploads and video streaming need separate load profiles.

For example, use **ten already-provisioned generators**. On generator 1:

```bash
k6 run --execution-segment '0:1/10' \
  --execution-segment-sequence '0,1/10,2/10,3/10,4/10,5/10,6/10,7/10,8/10,9/10,1' \
  --console-output video50k-shard01.log load_tests/video_request_burst.mjs
```

Generator 2 uses `1/10:2/10`, continuing through generator 10 using `9/10:1`.
Keep the full 50,000 target on every generator: k6 partitions it into 5,000
VUs per machine and assigns globally unique `vu.idInTest` values. Do not set
`VIDEO_LOAD_USERS=5000` on each shard, reuse segments, or launch repeated
iterations. Retain each k6 exit status; every shard must pass its thresholds.

## Evidence and gates

Collect all shard logs (they contain ordinal/timing/status evidence, no tokens
or student UUIDs), then merge them:

```bash
python -m load_tests.video_burst_report video50k-shard*.log \
  --run-id "$VIDEO_LOAD_RUN_ID" --deployed-sha "$VIDEO_LOAD_DEPLOYED_SHA" \
  --release-at-ms "$VIDEO_LOAD_RELEASE_AT_MS" \
  --output load_tests/results/video50k-client-report.json
```

The report rejects missing/duplicate/out-of-range ordinals, mismatched runs or
revisions, failed checkouts, fewer than 50,000 overlapping client request
intervals, and dispatch outside the one-second release window. Existing gates
remain p95 <=1,000 ms, p99 <=2,000 ms, failures <=1%, and 5xx <=0.1%; this burst
also requires every student's checkout contract to validate successfully.

**Client in-flight intervals include connection and OS queues.** A passing
client burst alone never certifies the application. The report deliberately
keeps `server_capacity_verified=false`. Separately capture actual server
in-flight requests, proxy queueing, DB pool/locks/CPU/memory, Redis/Celery lag,
storage latency, generator saturation and error rate. Reconcile exactly one
pending request and private document per student, no paid transitions, no
cross-student access, and no outbound delivery. Record target image/revision,
machine counts/specifications and the maximum *observed* server concurrency.
Do not publish 50,000 simultaneous submissions as verified until those gates,
all k6 shards and the merged client report pass on the deployed revision.

CI tests validate the harness with an offline 50,000-entry manifest, synthetic
interval parsing and a **four-user loopback mock** split across two k6 segments.
Neither offline fixtures nor the mock establish Amaris throughput.

References: [k6 executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/per-vu-iterations/),
[execution segments](https://grafana.com/docs/k6/latest/using-k6/k6-options/reference/#execution-segment),
[large test guidance](https://grafana.com/docs/k6/latest/testing-guides/running-large-tests/).
