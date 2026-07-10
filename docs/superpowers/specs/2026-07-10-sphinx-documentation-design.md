# Sphinx documentation redesign

## Goal

Make the published GitHub Pages site the authoritative, concise English guide
for `cft-piastq`, including standard PyPI installation and an API reference that
is organized by public class.

## Scope

- Rewrite the Sphinx user-guide pages in `docs/source/`.
- Replace editable-install instructions for end users with `pip install
  cft-piastq` and documented optional extras.
- Remove stale claims about direct and fake sampler execution being future work.
- Keep deployment instructions and Sphinx infrastructure intact.
- Split the API reference into a landing page plus dedicated pages for
  `PiastQClient`, `PiastQSampler`, `PiastQJob`, and `PiastQSamplerOptions`.

## Information architecture

The landing page gives the package purpose, the normal install command, and a
short local fake-mode example. The user guide uses focused pages: getting
started, execution modes, configuration, managed dashboard work, and results.

The API landing page links to one class per page, then to a small module
reference for lower-level helpers. Each class page uses `automodule` and a short
description of when to use the class, avoiding a single long auto-generated
listing.

## Accuracy and style rules

- Examples use `os.environ` and placeholder URLs; never literal credentials.
- `auto` can resolve to managed or direct, never fake.
- `counts()` is documented as an estimated integer view of quasi distributions.
- Direct and fake sampler execution are supported, subject to their optional
  dependencies.
- The style is plain English, short paragraphs, concrete commands, and no
  internal endpoint inventory unless it is needed to use the public API.

## Verification

- Build the Sphinx site with `python -m sphinx -b html docs/source
  docs/_build/html`.
- Confirm the generated navigation contains dedicated client, sampler, job, and
  options API pages.
- Run the Python test suite to check README snippets and public API behavior.
