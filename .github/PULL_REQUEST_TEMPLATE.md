## Summary

<!-- What does this PR change and why? -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactor / cleanup
- [ ] CI / tooling

## Testing

<!-- How did you verify this works? -->

- [ ] Imports pass: `python -c "from backend.server import app; print('OK')"`
- [ ] Tests pass: `pytest tests/`
- [ ] Manual smoke test: ran `python run.py scrape --query "..." --max-results 5 -o /tmp/test.csv`
- [ ] Web UI loads and responds (if frontend touched)

## Checklist

- [ ] My code follows existing patterns in the codebase
- [ ] No new lazy imports inside hot-path functions
- [ ] If I added a new ScrapeRequest field, I also added it to the CLI
- [ ] If I added a new config option, I documented it in `mapo.yaml`
- [ ] README or CONTRIBUTING.md updated if user-facing
