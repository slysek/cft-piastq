# Security

## Private reporting

Do not open a public issue containing a credential, token, private endpoint,
circuit payload, or provider response. Report security issues privately through
GitHub private vulnerability reporting when enabled, or through an agreed
private channel.

## Exposed secrets

If a secret may have been exposed, revoke or rotate it immediately. Deleting a
file or rewriting Git history is not enough because copies may still exist.

## Safe handling

Do not put secrets in source code, notebooks, outputs, screenshots, logs, or CI
configuration.
