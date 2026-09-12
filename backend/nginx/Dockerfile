FROM nginx:1.29-alpine

# Keep the Nginx version line stable while applying all available fixed Alpine
# packages from the image's configured repositories. The resulting image is
# scanned with a fail-closed HIGH/CRITICAL Trivy gate before release.
RUN apk upgrade --no-cache
