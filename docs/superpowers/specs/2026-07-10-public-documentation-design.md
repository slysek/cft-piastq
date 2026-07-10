# Public documentation redesign

## Goal

Replace the current mixed-language, partly stale documentation with clear English
documentation for the public `cft-piastq` package. Make the standard PyPI
installation path visible at the top of the user journey.

## Scope

- Rewrite `README.md` as the concise landing page used by GitHub and PyPI.
- Rewrite `docs/website-documentation.md` as the longer user guide.
- Keep all prose, headings, tables, and code samples in English.
- Document `pip install cft-piastq` and the `direct` and `fake` optional extras.
- Use only the currently exported public API: `PiastQClient`, `PiastQSampler`,
  and `PiastQJob`.
- Describe managed, direct, fake, and auto execution modes, configuration
  environment variables, and secret-handling expectations.

## Content design

### README

The README will lead with installation, followed by a minimal fake-mode example
that users can run locally. It will briefly explain the four modes, link to the
full guide, and include a short security note. It will avoid repeating the
endpoint contract and detailed result semantics.

### Full guide

The guide will contain:

1. Installation and extras.
2. A quick-start circuit submission example.
3. Configuration precedence and environment variables.
4. A concise table explaining each execution mode and when to choose it.
5. Focused examples for managed, direct, fake, and auto modes.
6. Sampler options and result/count semantics.
7. Security guidance for PCSS tokens and dashboard API keys.

## Accuracy rules

- Examples use placeholder URLs and environment variables, never literal
  credentials.
- Claims reflect the current implementation and public README: managed, direct,
  and fake sampler execution are supported; `auto` chooses managed or direct
  and never silently chooses fake mode.
- `counts()` is described as an estimated integer view of quasi distributions,
  not raw provider memory.

## Verification

- Confirm both files are UTF-8 English text with no mojibake.
- Compare referenced classes, parameters, option names, and environment
  variables with `src/cft_piastq`.
- Build the package metadata to ensure the rewritten README remains acceptable
  as the PyPI long description.
