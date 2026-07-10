# Adapter registry

`scripts/register-adapter.sh` validates candidate metadata then writes it below
`~/models/adapters/<role>/`. Status `approved` is rejected: promotion and current
symlink changes are manual-only. Mistral heavy judge is never a registry target.
