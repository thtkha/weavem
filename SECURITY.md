# Security policy

## Report a vulnerability privately

Email **Kha Trịnh** at **khaa.dev@gmail.com**. Include the Weavem version, affected
component, expected and actual behavior, and a minimal reproduction using
synthetic data. Describe the potential impact and any safe workaround.

Do not post exploit details in a public GitHub issue. Do not include API tokens,
passwords, private keys, customer data, or production task stores. If a sensitive
attachment is needed, describe it first and agree on a private transfer method.
There is no guaranteed response or remediation timeline for this alpha project.

## Supported release and trust boundary

The current documented release is `0.1.0a2`, an experimental headless alpha.
The editor branch and newer core-contract work are unreleased. Reports about
those branches are welcome, but their presence in the public repository is not
a claim that they ship in the PyPI package.

Weavem does not sandbox task or flow code. Imported Python/native artifacts run
with the calling process's privileges. Use only publishers you trust; a checksum
verifies bytes, not publisher identity. Do not submit real malicious artifacts
or run a suspected payload merely to prepare a report.

For non-security bugs and feature requests, use the
[repository issue tracker](https://github.com/thtkha/weavem/issues).
