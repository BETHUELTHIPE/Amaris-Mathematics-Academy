# Monthly encrypted production application backups

This is an automated **monthly** backup policy, not a weekly backup requirement.

- Source: production PostgreSQL `public` application schema, read-only from the Render-managed production database URL
- Frequency: **1st day of every month at 04:17 SAST** (`17 2 1 * *`, UTC)
- Backup format: PostgreSQL 17 custom dump encrypted with GPG AES-256
- Validation: decrypt a copy and restore into an isolated, network-disabled PostgreSQL 17 container; compare restored and source application record counts
- Destination: **encrypted GitHub Actions artifact only**, with **90-day retention** (repository retention policy may impose a lower cap)
- Production writes: **none**. No migrations are run by the backup workflow.
- Current scope: `public` application schema. **Supabase Auth, Storage objects, and other managed schemas are not included.** These need independent disaster-recovery coverage.

## One-time configuration

The monthly process does **not** need manual initiation each month, but it cannot securely encrypt a *recoverable* backup without a lasting recovery secret.

1. Generate and securely retain a unique backup recovery passphrase of **at least 32 random characters**. Keep a separate, private copy outside the production database and this public repository; **do not put the passphrase in GitHub issues or chat**.
2. In GitHub, go to **Settings → Environments → production → Environment secrets → Add secret**. Name the secret `AMARIS_BACKUP_PASSPHRASE`, paste the value and save. This is done **once**.
3. For an initial baseline before any production schema migration, open **Actions → Genuine Encrypted Production App Backup and Isolated Restore → Run workflow** on `main` and set confirmation to `BACKUP_PUBLIC_SCHEMA_ONLY`. Check for a successful run and an encrypted artifact.
4. Thereafter, the first-of-month schedule runs with no manually entered confirmation.

If the secret is missing, the workflow **fails closed** before reading the production database. An unencrypted backup is **never** uploaded. The repository is public, so recovery material must not be placed in it.

## Recovery instructions

To restore an encrypted artifact, a trusted operator needs the artifact, the separately retained `AMARIS_BACKUP_PASSPHRASE`, and a **new isolated** PostgreSQL target. Decrypt with GPG locally and use `pg_restore` with full reviews of existing database objects and Supabase-managed cross-schema dependencies. **Never restore over the live production database during a verification exercise.**

Keep in mind: Actions artifacts are retained for at most 90 days in public repositories. At least one valid encrypted backup and its recovery passphrase should also be archived outside the public repository for more durable disaster recovery when that becomes available.

## Release policy

- Production development and CI may continue without a weekly backup gate.
- A **fresh retained encrypted backup** is still required before any risky or irreversible production schema migration; a successful synthetic CI backup or a short-lived restore proof alone is not a substitute.
- A new major release still requires passing tests, an explicit approved production promotion, and rollback/restore instructions.
- Check every month that a **successful** scheduled run produced the expected encrypted artifact; a configured schedule is not evidence that the backup completed.
