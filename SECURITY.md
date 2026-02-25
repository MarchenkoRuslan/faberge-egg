# Security Policy

## Reporting Vulnerabilities

Please report security issues privately (e.g. via maintainer contact) rather than public issues.

## Known Limitations

### python-ecdsa (transitive via python-jose)

- **CVE-2024-23342** (Minerva timing attack on P-256): python-ecdsa maintainers do not plan a fix.
- **Risk**: Low — we use HS256 for JWT, not ECDSA. The vuln affects ECDSA signing/keygen only.
- **Mitigation plan**: Migrate from python-jose to PyJWT (uses cryptography). Dependabot ignore: see `.github/dependabot.yml`.
