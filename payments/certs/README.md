# B2C security certificate

This folder is where your Safaricom-issued public certificate goes, used
to encrypt the B2C initiator password (see the main README's "Wallet
withdrawals" section for the full setup).

- **Sandbox**: download `SandboxCertificate.cer` from the Daraja portal's
  B2C documentation page and save it here as `sandbox_cert.cer`.
- **Production**: Safaricom issues a separate production certificate once
  your B2C application is approved — save it here as `production_cert.cer`
  and point `MPESA_B2C_CERT_PATH` at it in your production environment.

**Never commit a real production certificate to a public repository.**
This folder is already covered by a `.gitignore` entry for `*.cer` — if
you fork/copy this project, double check that stays in place.
