# Security policy

## Supported versions

Thadam is in early development. Security fixes target the latest code on `main`. Check `pyproject.toml` for the source version and include the exact commit in reports. Use the latest revision when reporting or verifying an issue.

| Version | Security maintenance |
| --- | --- |
| Latest revision of `main` | Supported |
| Older commits, tags, and release lines | No separate security backports; update to the latest revision |

This policy will be updated when Thadam maintains published release lines.

## Report a vulnerability privately

Use GitHub's [private vulnerability reporting form](https://github.com/thadam-ai/thadam/security/advisories/new). You can also find it under **Security → Advisories → Report a vulnerability** in the repository.

Please do not disclose vulnerability details in public issues, discussions, or pull requests before a fix or coordinated disclosure is agreed.

Include, where possible:

- The affected Thadam version or commit, Python version, and optional integration versions.
- A description of the issue, its impact, and the conditions needed to trigger it.
- Minimal reproduction steps or a proof of concept using synthetic data.
- Any suggested mitigation or fix.

Remove API keys, credentials, customer data, and other sensitive information from examples and reports. Do not access other people's systems or data to demonstrate an issue.

Maintainers will use the private report to investigate, discuss a fix, and coordinate disclosure. Thadam does not currently guarantee a response or remediation timeline.

## Execution and data boundaries

Thadam runs trusted agent modules, tools, and Python verifiers in the current process with the invoking user's permissions. It does not sandbox code or enforce execution timeouts. Only run agent code and integrations you trust; a test suite is not an isolation boundary.

Reports can contain agent inputs and outputs, tool arguments and results, and exception messages. Automatic secret redaction is not implemented. Review these artifacts before sharing them or uploading them in CI.

Unexpected execution beyond these documented boundaries, validation bypasses, unintended disclosure, and dependency vulnerabilities affecting Thadam are appropriate subjects for private reports. Ordinary behavior bugs and feature requests can use [public issues](https://github.com/thadam-ai/thadam/issues).
