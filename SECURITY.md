# Security notes

PagePulse is a local competition/demo project. It does not include user accounts, a production-grade job queue, or hardened network isolation.

## Keep secrets out of Git

- Do not commit `.env`, `.streamlit/secrets.toml`, API keys, or provider credentials.
- `.env.example` is a blank reference file; it is not a place to store a real key.
- The `.gitignore` excludes local SQLite databases, screenshots, and the `data/` folder because they can contain monitored page content.
- If a credential is accidentally committed, revoke it with its provider and remove it from repository history; deleting it in a later commit is not enough.

## Scope and safe use

The URL check blocks many local and private addresses, but this is not a complete defense against DNS rebinding or unsafe browser subresource requests. Do not expose the app to untrusted users or deploy it as a public service without additional security work.

Monitor only pages you are authorized to access and respect the site's terms and request limits.

## Reporting a vulnerability

For a public GitHub repository, use GitHub's **Report a vulnerability** feature under the repository's Security tab when private vulnerability reporting is enabled. Avoid posting credentials or exploit details in a public issue.
