# Visual baselines for the atlas-fidelity gate

`current/<workspace>-<viewport>.png` are the approved "current" reference captures
that `tests/browser/test_atlas_fidelity.py` compares against (workspace +
desktop/mobile-s). Update them deliberately ONLY after an approved visual change:

```
APP_URL=http://127.0.0.1:8081 UPDATE_BASELINES=1 \
  python3 -m pytest tests/browser/test_atlas_fidelity.py -q
```

The gate also asserts semantics (workspace section visible, no horizontal
overflow, a command header present) so a blank-but-similarly-colored page cannot
pass. `ATLAS_DIFF_THRESHOLD` (default 0.015) sets the allowed pixel-drift ratio.
