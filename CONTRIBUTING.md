# Contributing documentation

[English](CONTRIBUTING.md) | [Português (Brasil)](CONTRIBUTING.pt-BR.md)

## Update both languages together

Author-owned documentation has an English `.md` file with an English filename and a Brazilian Portuguese `.pt-BR.md` counterpart in the same directory. The canonical README is English.

When changing instructions or documented behavior:

1. Update both versions in the same change.
2. Add the language switch at the top of each page.
3. Keep internal links within the reader's language, except the language switch.
4. Check heading anchors after translating a heading; anchors can differ by language.
5. Preserve command syntax, paths, identifiers, constants, equations, API signatures and executable examples. Actual logs and runtime messages may remain in their original language; explain them in the surrounding prose.
6. Preserve historical notices and dates. Translating a past verification does not mean its commands were run again.
7. Check that every linked local document exists and code fences are balanced.

Example for a document named `HOST`:

```markdown
[English](HOST.md) | [Português (Brasil)](HOST.pt-BR.md)
```

Translate all explanatory content, including tables and diagram labels, without silently removing limitations or replacing full chapters with summaries.

## Scope

This convention applies to repository-authored documentation, including model packages, the independent ESP32 host and archived chapters under `docs/historico/`.

Do not translate or edit installed dependency documentation, virtual environments, Git metadata, or build-generated files. Preserve executable source code and generated artifacts unless a separate implementation task calls for changes.

English filenames use English terms. Portuguese filenames retain their existing names and the `.pt-BR.md` suffix. Use the language links to identify each pair; the base filenames may differ.

