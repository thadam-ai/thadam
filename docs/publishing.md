# Publishing Thadam to PyPI

**Status:** [`thadam-ai` v0.3.0](https://pypi.org/project/thadam-ai/0.3.0/) was published on 2026-10-30 through the [GitHub release](https://github.com/thadam-ai/thadam/releases/tag/v0.3.0) and Trusted Publishing workflow. GitHub's `pypi` approval environment is configured. Later features on `main` await a follow-up release.

## Published release and current checkout

Version 0.3.0 includes the local runner, SDK/CLI, optional LangGraph tracing, tool
assertions, and saved-report regression comparison. Install that release with:

```shell
python -m pip install 'thadam-ai==0.3.0'
```

Repeated-evaluation reliability gates, suite revisions and baseline review, the
dashboard, async execution, and scenario suggestions were added after this tag.
Use a source checkout for those workflows and their newer report contracts until
a release containing them is published. Installing PyPI v0.3.0 does not provide
the `dashboard` or `ai` extras.

## Names

| Purpose | Name |
| --- | --- |
| Product | Thadam (தடம்) |
| PyPI distribution / installation | `thadam-ai` / `python -m pip install thadam-ai` |
| Python import | `thadam` |
| CLI / module command | `thadam` / `python -m thadam` |
| Optional integration | `python -m pip install 'thadam-ai[langgraph]'` |

Distribution and import names are independent; preserving the current import and CLI keeps existing integrations working. See the [Python packaging explanation](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/). The separate PyPI project named `thadam` is unrelated to this repository; do not use it to install this SDK.

The `thadam-ai` project is registered on PyPI and its 0.3.0 wheel and source distribution are available. Keep using this distribution name for future releases.

## One-time owner setup

The initial setup is complete. Use this checklist when restoring the release
configuration or adding a publisher for a new project.

1. Verify the PyPI account's email, generate and safely store recovery codes, and enable 2FA. Follow [PyPI's account instructions](https://docs.pypi.org/your-account/two-factor-authentication/). Keep recovery codes and authentication secrets out of this repository and chat.
2. Ensure `.github/workflows/publish.yml` exists on `main` and all required repository CI checks pass.
3. Review [GitHub environment settings](https://github.com/thadam-ai/thadam/settings/environments). This repository's `pypi` environment is configured with `kinba09` as required reviewer and a selected `v*` tag rule. When recreating it, use those settings. While you are the only release maintainer, leave **Prevent self-review** off so you can approve releases you trigger. See [GitHub environment configuration](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
4. For the existing PyPI project, verify its GitHub Trusted Publisher settings use the values below. When creating a new project, add a **pending GitHub Trusted Publisher** through [PyPI account publishing](https://pypi.org/manage/account/publishing/) with the corresponding project/repository values:

| PyPI form field | Value |
| --- | --- |
| PyPI project name | `thadam-ai` |
| Repository owner | `thadam-ai` |
| Repository name | `thadam` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

The workflow field is just the filename, not `.github/workflows/publish.yml`. The environment name must match on both services. No long-lived PyPI API token or GitHub secret is needed. A pending publisher does not reserve the package name; it creates the project on its first successful upload. See [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) and [publishing with OIDC](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Validate before publishing

Run **Publish to PyPI → Run workflow** from GitHub Actions on `main`. A manual run validates and saves distributions, and skips the publishing job. It does not upload to PyPI.

The build job checks dependencies, lint, formatting, and the full test suite with LangGraph. It builds a wheel from the source distribution, validates both files' metadata, installs the wheel in a fresh environment, and checks the installed distribution name/version, type marker, SDK, report loading/comparison, and CLI outside the checkout. The core remains free of runtime dependencies.

Local equivalents, from a clean checkout with Python 3.14:

```shell
python -m pip install -e '.[dev,langgraph]' build twine
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m pytest -q tests examples/regression_test.py
python -m build
python -m twine check --strict dist/*
```

Build into an empty output directory so old wheels are not mixed with the release. The CI and release jobs each use a fresh checkout. `scripts/check_installed_package.py` checks the installed wheel; running it against an editable installation does not verify distribution contents.

## Publish a version

1. Confirm the manual validation run and the main-branch CI run passed, and review the built artifacts.
2. Choose a new version and update both `pyproject.toml` and `thadam.__version__` to match. Version `0.3.0` is already published and cannot be reused for changed content.
3. Create a GitHub release with tag **`v<package-version>`**, targeting the reviewed commit on `main`, and publish the release. For example, the first release used `v0.3.0`; use a new matching version for the next release. Publishing this GitHub release triggers the upload workflow.
4. Wait for the build job, then review and approve the `pypi` environment deployment. This is the final approval for the public PyPI upload.
5. Confirm the publish job succeeded and that the expected files and provenance appear on the PyPI project page.

The workflow checks that the tag matches the package version and that the tagged commit belongs to `main`. The build job has read-only repository permissions. Only the separate publish job receives `id-token: write`; it downloads the validated artifacts from that same run and uploads them with PyPA's pinned action and attestations enabled.

Manual runs and ordinary CI do not publish. Fork releases are excluded from the publishing job. Do not replace the release trigger with `pull_request_target`, expose publishing credentials to candidate code, or add `skip-existing` to hide version conflicts.

After publishing, verify a fresh environment rather than a source checkout. This
example checks the existing 0.3.0 release; substitute the newly published version
when validating a later release:

```shell
python -m venv /tmp/thadam-pypi-check
/tmp/thadam-pypi-check/bin/python -m pip install 'thadam-ai==0.3.0'
/tmp/thadam-pypi-check/bin/python -c "from importlib.metadata import version; import thadam; print(version('thadam-ai'), thadam.__version__)"
/tmp/thadam-pypi-check/bin/thadam --version
```

These virtual-environment paths use macOS/Linux syntax; on Windows use the environment's `Scripts` directory. Verify the optional extra separately when releasing integration changes. For each new release, confirm the upload job and published files on PyPI; local builds alone do not prove publication.

## Failed or partial releases

Inspect the publish job and the PyPI project before retrying. PyPI does not allow replacing previously uploaded filenames. Correct the underlying problem, and use a new version when the published content needs to change. If a version was uploaded but should not be used, assess whether to yank it rather than trying to overwrite it. See [PyPI upload troubleshooting](https://docs.pypi.org/publishing/troubleshooting/) and [yanking guidance](https://docs.pypi.org/project-management/yanking/).
