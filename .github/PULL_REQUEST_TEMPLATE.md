## Summary

<!-- Two or three sentences on what this PR changes and why. -->

## Linked issue

<!-- e.g. Closes #42. Skip if there's no tracking issue. -->

## Type of change

<!-- Check all that apply. -->

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] Tests / CI
- [ ] Build / packaging
- [ ] Security hardening

## Checklist

- [ ] Tests added or updated for the change
- [ ] All tests passing locally (`uv run pytest` and, if `ui/` touched, `cd ui && go test ./...`)
- [ ] If both Python and Go layers are affected, parity is maintained (same contract, mirrored validation)
- [ ] User-facing changes reflected in `README.md` (or `ui/README.md` for desktop UI changes)
- [ ] No secrets or credentials in commits
- [ ] No `print` / debug logging left in production code paths

## Notes for the reviewer

<!-- Anything specific to look at, known limitations, follow-ups planned, etc. -->
