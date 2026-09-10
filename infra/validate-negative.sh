#!/usr/bin/env bash
set -euo pipefail
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
for pattern in 'AWS::IAM::Role' 'NatGateway' 'MultiAZ: true' 'MonitoringInterval: 5' 'PubliclyAccessible: true' 'FromPort: 5432 CidrIpv6: ::/0'; do
  printf '%s\n' "$pattern" >"$tmp"
  case "$pattern" in
    *'FromPort: 5432'*) rg -U 'FromPort:\s*5432.*?(CidrIp:\s*0\.0\.0\.0/0|CidrIpv6:\s*::/0)' "$tmp" >/dev/null || { echo "negative check failed: $pattern" >&2; exit 1; } ;;
    *) rg -n 'AWS::IAM::|NatGateway|MultiAZ:\s*true|MonitoringInterval:\s*[1-9]|PubliclyAccessible:\s*true' "$tmp" >/dev/null || { echo "negative check failed: $pattern" >&2; exit 1; } ;;
  esac
done
echo 'negative infrastructure checks passed'
