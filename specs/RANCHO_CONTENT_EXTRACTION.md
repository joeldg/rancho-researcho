# Rancho Web Content Fetching and Extraction Contract

## Scope

This project-scoped contract governs how Rancho fetches arbitrary, untrusted result URLs and
converts them into bounded markdown evidence for later synthesis: outbound request containment
(SSRF), resource bounds, redirect handling, content-type limits, and HTML-to-markdown
extraction. It narrows `GLOBAL_SECURITY.md` and `RANCHO_API_SECURITY.md` for the outbound
fetch surface.

## Intent

Rancho must read the open web without becoming an SSRF vector into internal infrastructure,
without unbounded resource consumption, and without trusting or executing page content. Fetched
bytes are evidence, never instructions, and a fetch that cannot be completed safely fails
explicitly rather than fabricating content.

## Requirements

1. Only `http` and `https` URLs are fetchable. Before a connection is made, every IP the host
   resolves to is vetted, and any address in a private, loopback, link-local, multicast, or
   otherwise reserved range (IPv4 and IPv6) causes the fetch to be refused. The socket must
   connect to a vetted IP so that a name re-resolving to a different address (DNS rebinding) does
   not bypass the check.
2. Redirects are followed only to a bounded depth, and every redirect hop is re-vetted under the
   same address policy. A redirect to a disallowed address, an unsupported scheme, or a detected
   redirect loop is refused.
3. Every fetch enforces bounded connect and read timeouts and a maximum response body size,
   stopping the download once the cap is exceeded rather than buffering unbounded content. The
   response content type must be within an allowlist of HTML types (for example `text/html` and
   `application/xhtml+xml`); other content types are refused.
4. Requests send an honest, rotating User-Agent from a small fixed set and carry no ambient
   credentials, cookies, caller tokens, or tenant secrets to the target. No secret-bearing header
   is ever sent to an untrusted host.
5. HTML-to-markdown conversion removes scripts, styles, forms, iframes, navigation, headers,
   footers, and sidebars and never executes JavaScript. It preserves links, tables, and headings
   so evidence keeps context. The emitted markdown is bounded in size.
6. Fetched content is treated strictly as untrusted data. Extracted text is never interpreted as
   commands or configuration and is kept isolated for later, explicitly delimited prompt
   construction. (Full prompt-injection verification is a separate later-phase concern.)
7. A refused, failed, timed-out, oversized, or disallowed fetch raises a typed error. Callers
   record an explicit skipped or unavailable evidence outcome and never fabricate page content,
   citations, or a canonical URL that was not actually retrieved.

## Non-Goals

This contract does not define JavaScript rendering or a headless browser, a robots.txt policy
engine, the deep-research crawl loop, LLM synthesis, response caching, or full prompt-injection
detection. Those are governed elsewhere or in a later phase.

## Acceptance Evidence

- Tests prove refusal of URLs resolving to private, loopback, link-local, and reserved IPv4 and
  IPv6 addresses, and refusal when a resolved address changes between check and connect.
- Tests prove bounded redirect depth with per-hop re-vetting, redirect-loop refusal, response
  size-cap enforcement, and content-type allowlisting, with no live network.
- Tests prove HTML-to-markdown drops scripts/styles/navigation and preserves links, tables, and
  headings, and that output is size-bounded.
- A failed or refused fetch yields an explicit unavailable/skipped evidence outcome, never
  fabricated content.
- Code trace mappings connect the fetcher, address vetting, extractor, and tests to this
  contract.

## Token Budget Class

Project contract.

## Related Specs

- `GLOBAL_SECURITY.md`
- `RANCHO_API_SECURITY.md`
- `SECURITY_AND_SECRETS.md`
- `RANCHO_ASYNC_RESEARCH.md`
- `RANCHO_PROJECT_PROFILE.md`

## AI Agent Directives

Implement the fetcher and extractor only after this contract is reviewed and published. Never
follow a redirect without re-vetting the target address, never send secrets to an untrusted host,
never execute page script, and never emit evidence for a URL that was not safely retrieved.
