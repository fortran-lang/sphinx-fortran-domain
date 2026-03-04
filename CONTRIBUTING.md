# Contributing to Sphinx Fortran Domain

Thanks for your interest in improving this project.

## Getting started

1. Fork and clone the repository.
2. Create and activate a virtual environment.
3. Install the project with development extras:

```bash
pip install -e ".[test,docs]"
```

## Development workflow

1. Create a branch from `main`.
2. Make focused changes with clear commit messages.
3. Run tests locally before opening a pull request:

```bash
python -m pytest -q
```

4. If your change affects docs or rendering, build docs locally:

```bash
cd docs
make html
```

## Code guidelines

- Keep changes minimal and focused on one problem.
- Follow the existing style and naming patterns in the codebase.
- Add or update tests when behavior changes.
- Avoid unrelated refactors in the same PR.

## Documentation guidelines

- Update `README.md` and/or `docs/` when user-visible behavior changes.
- Include examples for new directives, roles, or configuration options.

## Pull request checklist

- Tests pass locally.
- Documentation updated (if needed).
- Backward compatibility considered for existing config and API usage.
- PR description explains motivation and scope.

## Reporting issues

Please open a GitHub issue with:

- Expected behavior
- Actual behavior
- Minimal reproduction
- Environment details (Python, Sphinx version, OS)

## Questions

If you are unsure about an implementation approach, open a draft PR early so maintainers can provide direction.
