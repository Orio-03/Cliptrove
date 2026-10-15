# Security

Cliptrove runs a small web server on your own PC. It only listens on `127.0.0.1`, and every request needs a secret token that only its own page has. [How it works](docs/HOW-IT-WORKS.md#the-local-server-serverpy) has the details.

## Reporting a problem

If you find a way for another website, program or device to read someone's clip library or control Cliptrove, **please don't open a public issue**. Report it privately instead:

1. Go to [Security > Report a vulnerability](https://github.com/Orio-03/Cliptrove/security/advisories/new).
2. Describe what you found and how to reproduce it.

This is a one-person hobby project, so replies may take a few days. Please give it a reasonable time to be fixed before sharing details publicly.

## Supported versions

Only the latest release gets fixes.

## Checking a download

Each release lists the SHA-256 checksum of its zip in `SHA256SUMS.txt`. To check the zip you downloaded, run this in PowerShell and compare the result:

```
Get-FileHash .\Cliptrove-0.3.0-windows.zip -Algorithm SHA256
```

Only download Cliptrove from this repository's [Releases page](https://github.com/Orio-03/Cliptrove/releases).
