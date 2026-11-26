#!/usr/bin/env bash
# Bootstrap only a GitHub OIDC provider and ECR-publish-only role.
# No ECS service, ALB, database, cache or traffic is modified.
set -euo pipefail
export AWS_REGION=eu-north-1 AWS_DEFAULT_REGION=eu-north-1 AWS_PAGER=""
export AWS_PROFILE="${AWS_PROFILE:-amaris}"
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
template="$dir/github-oidc-ecr-publisher.yml"
account="$(aws sts get-caller-identity --query Account --output text)"
[[ "$account" == "110156539003" ]] || { echo "Refusing unexpected AWS account." >&2; exit 1; }
aws cloudformation validate-template --template-body "file://$template" >/dev/null
aws cloudformation deploy \
  --stack-name amaris-staging-github-oidc-publisher \
  --template-file "$template" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
role_arn="$(aws cloudformation describe-stacks --stack-name amaris-staging-github-oidc-publisher --query 'Stacks[0].Outputs[?OutputKey==`EcrPublisherRoleArn`].OutputValue | [0]' --output text)"
[[ "$role_arn" == "arn:aws:iam::110156539003:role/AmarisGitHubECRPublisher" ]]
echo "GitHub OIDC ECR publisher role is ready:"
echo "$role_arn"
