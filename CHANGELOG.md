# Changes

## 0.1.3 — 2 October 2026

- Recognise `chatgpt-bin` as **ChatGPT desktop** and `antigravity` as
  **Google Antigravity**, with short descriptions and product links.
- Preserve package identifiers, exact old/new versions and original log evidence.
- These are application descriptions, not claims about what a particular release
  changed. Version-specific release notes remain explicitly unavailable unless
  separately sourced by the existing exact-release matching logic.
- No changes to update detection, log-read limits, news settings or stored state.
- 33 tests pass, including new mapping/evidence and unknown-package fallback tests.

Product identification uses installed package metadata; Antigravity's description
was also checked against https://antigravity.google/product/antigravity-2.
