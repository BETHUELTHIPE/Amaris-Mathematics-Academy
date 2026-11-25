# Amaris AWS ECS native blue-green rollout (staging)

Status: prepared configuration only. No AWS changes are made by this branch.
Existing service: amaris-web-staging-alb, cluster amaris-ecs-staging, Stockholm.
The existing HTTPS gateway and ALB remain in service. No new ALB is required.

## Hard gates before enabling
- PR 457 combined application CI must pass, including PostgreSQL upgrade and rollback-compatibility tests, ARM64 builds, dependency/container scans and browser acceptance.
- Publish immutable backend/frontend ECR digests from the same verified candidate; save previous task definition and digest manifest.
- Existing EC2 task uses local Valkey and host bind mounts. Move cache/broker/results to a separately managed shared private service with authentication, backups and capacity. Remove task-local Redis overrides and volume from both revisions. Package proxy config in immutable images or otherwise ensure it is read-only and available on every eligible host.
- Ensure both revisions can run simultaneously, with sufficient CPU, memory and ENI capacity. Do not scale in the current serving task to make room. Confirm temporary compute costs against the existing staging budget.
- Back up PostgreSQL and rehearse restore. Apply expand-only migrations once in a dedicated task before green starts; disable automatic web-task migrations, ensure old and new code work against the expanded schema. Defer destructive changes until rollback window has ended.
- Keep Celery worker and Beat separately managed; one scheduler, safe idempotent processing, shared broker and compatible task payloads. Keep new externally visible payment and notification features disabled until acceptance.
- Configure a dedicated OIDC read-only role for the manual readiness workflow. No static credentials. Restrict role trust to this repository and protected staging environment. Inspect AWS permissions separately.

## Convert the existing service (planned, not automatic)
1. Take a snapshot of the existing listener actions, task definitions, ECS configuration and known-good health evidence.
2. Validate and deploy prerequisites.yml in a separate staging CloudFormation stack only after the gates above. This adds an alternate IP target group on port 8080 and ECS load-balancer infrastructure role; it does not change the current ALB.
3. Set up the existing ALB production listener rule with weighted forwarding to both target groups, current 100 and alternate 0. Create a separate private test listener/rule, scoped to a controlled test runner or gateway via security group rules. Do not use a public user-supplied header as authentication. Confirm the existing dualstack-without-public-ipv4 ALB works with native ECS routing; do not replace the ALB without review.
4. Attach ECS loadBalancers advancedConfiguration with alternateTargetGroupArn, productionListenerRule, testListenerRule and roleArn. Follow AWS documented existing rolling-to-blue-green migration sequence: first update advancedConfiguration and complete the rolling deployment using the known-good immutable revision with sufficient capacity and no downtime; then set strategy BLUE_GREEN using deployment-configuration.json. Never reuse the old 0/100 availability configuration. Validate initial conversion and rollback in staging before candidate deployment.
5. Use CloudWatch alarms for unhealthy targets, 5xx and application errors; enable rollback in the ECS deployment alarms configuration with real verified alarm names. Alarm configuration is intentionally not guessed.
6. Register the tested immutable candidate task definition and update the native blue-green service only after the CI, migration, security and rollback gates. Do not run the old rolling deployment workflow for feature promotion.

## Traffic and approval policy
- ECS scales green alongside blue. No normal traffic goes to green until tests pass.
- POST_TEST_TRAFFIC_SHIFT pause: check green image versions, health, anonymous authorization, login/OTP, private chat isolation, booking and sandbox payment/invoices, tutor/sponsor access, notifications and storage. Test with isolated data, no real payments or duplicate emails. Continue only after documented acceptance; otherwise request rollback. Timeout 30 minutes rolls back.
- POST_PRODUCTION_TRAFFIC_SHIFT pause: verify public endpoint and monitor both revisions; rollback on failures. Timeout 15 minutes rolls back.
- Bake for 15 minutes after approval; ECS retires the old revision on success. Preserve previous immutable images/task definition for future recovery. Extend timing only after budget review.
- Blue and green labels refer to active and candidate revisions, not permanent colors; determine active target group from live routing on every deployment.

AWS docs:
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/update-rolling-to-bluegreen.html
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/alb-resources-for-blue-green.html
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/pause-lifecycle-hooks.html

The current application release and runtime architecture are not yet verified. This runbook and the supplied configuration do not authorize live conversion or traffic changes.


## Implemented candidate preparation
- shared-valkey.yml defines an optional encrypted, private, single-node staging replication group with no eviction, AUTH, snapshots and restricted ingress. It is not a high-availability production configuration. Check Stockholm availability and total cost before provisioning.
- proxy/ packages the existing staging gateway routing as an immutable container. Build with a reviewed ARM64 nginx digest; publish to staging ECR only after scanning.
- render-stateless-task.py accepts the current ALB task definition and three immutable ECR digests. It removes task-local Valkey and all proxy bind mounts, and references four separate SecureString URL parameters. Run its unit tests before registering a task.
- Use rediss:// authenticated URLs with certificate verification (Celery broker/result URLs must explicitly require certificate validation), and separate logical databases 0,1,2,3 for private cache, public cache, broker and results. Provision parameters under /amaris/aws-staging/shared-valkey/{cache,public-cache,broker,result}. Update the ECS execution role to read only these parameters and the required KMS key. Do not print URLs or credentials.
- Before moving queues, stop producers/schedulers using a controlled maintenance procedure, drain workers or preserve queued work with a verified migration, validate pending outbox records and reconcile. A cache flush is not an acceptable broker migration. Do not switch blue to a second broker while green uses a different broker.
- Combined application CI now builds the frontend before its render tests; the backend uses the integrated application Dockerfile. It scans both ARM64 images and archives successful candidates with SHA256 checksums. A release must use both images from the same fully successful run.
- No AWS execution or resource provisioning has been verified. The new workflow must be made available for dispatch under GitHub's default-branch workflow rules or its read-only preflight run locally using the authorized AWS CLI profile.
