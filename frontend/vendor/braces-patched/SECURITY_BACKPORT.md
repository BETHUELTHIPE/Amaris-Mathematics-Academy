# Amaris braces security backport

This package starts from the published `braces@3.0.3` source and applies the
upstream proposed fix from micromatch/braces pull request #72, head commit:

`28d440b5dd449dbf1fe6f3506cf94ecca4d02660`

The backport adds a maximum structural nesting depth to parsing, compile,
expand and stringify paths to address CVE-2026-93687 /
GHSA-vfj7-8cjw-p6xm while no patched npm release exists.

The package version is intentionally `3.0.4-amaris.0` so dependency scanners
can distinguish this patched local package from vulnerable upstream 3.0.3.

Upstream remains MIT licensed; the upstream LICENSE is included unchanged.

Exit condition: remove this local backport and use the official upstream
release once micromatch/braces publishes a version that fixes
GHSA-vfj7-8cjw-p6xm and the full frontend test suite passes with it.
