# Build Week release checklist

The candidate tag is `v0.6.0-build-week`. Do not create it until the pull
request for issue #13 is merged, every repository gate passes on the merge
commit, and the user explicitly requests release.

## Repository-owned gates

- [x] Public repository has an MIT license.
- [x] Package version and submission metadata say `0.6.0`.
- [x] Frozen report and packaged replay have SHA-256
  `689698a2525cb77142a3aae33295ef6d7de18a6d0bb848c85546f70c61acf490`.
- [x] README, report, demo script, and submission copy use 9/9 vs 9/9,
  249.089/186.590 seconds, and 766,538/562,358 tokens.
- [x] Zero-credit replay is labeled historical and needs no rebuild, external
  CLI, network request, credential, or model credit.
- [x] Live smoke path and macOS/Linux CPython 3.10–3.14 support are explicit.
- [x] Architecture, paired benchmark, evidence-boundary diagrams are present.
- [x] Demo script is under three minutes and opens on the result.
- [x] Challenges diary contains exact observed failures and mitigations.
- [x] Full tests, Ruff, sdist/wheel build, clean wheel install, and CI pass.

## External gates

- [x] Run `/feedback` in the primary Codex collaboration session and enter the
  returned ID as `external.feedback_session_id`.
- [x] Record the demo at no more than 2:50 and show the result in the first 15
  seconds.
- [x] Watch the recording as a new judge; check legibility and remove secrets.
- [x] Upload the video publicly or unlisted and enter its HTTPS URL.
- [x] Populate the Devpost project and enter its public project URL.
- [ ] Finalize the submission form in the Developer Tools category.
- [x] Run `sigmap-bridge submission validate submission/build-week-2026.json
  --require-ready` and require exit code 0.
- [x] Confirm README, video, Devpost copy, and report still show identical
  commands and numbers.
- [ ] Submit no later than the internal buffer deadline:
  2026-07-21 05:00 PDT, twelve hours before the official deadline.
- [ ] Record the final submission time and confirmation outside this repository.

## Final release commands

Run only after merge and explicit approval:

```bash
git switch main
git pull --ff-only origin main
sigmap-bridge submission validate submission/build-week-2026.json --require-ready
python -m unittest discover -s tests -v
ruff check .
python -m build
git tag -a v0.6.0-build-week -m "SigMap Codex Bridge Build Week candidate"
git push origin v0.6.0-build-week
```
