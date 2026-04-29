# AGENTS

## Purpose
- This directory contains the `entropy_audit` Python package, a CLI tool for entropy governance reports.
- It collects project facts, normalizes metrics, scores governance dimensions, and renders monthly/quarterly reports.
- Code-native entropy is handled inside this package and should not depend on old external local tools.

## Package Structure
- `cli.py`: command entry point for `init`, `collect`, `score`, `report`, and `run`.
- `config.py`: parses `entropy.config.toml` into typed configuration objects.
- `collectors/`: currently exposes code entropy collection through `collectors/code_entropy_collector.py`.
- `reporter/`: renders the HTML dashboard and code entropy detail pages/exports.
- `lang/`: language adapter layer. Java is currently the supported implementation.
- `lang/java/analyzers/`: Java structure, semantic, behavior, cognition, and style entropy analyzers.
- `lang/java/scoring_v1_schema.py` and `lang/java/scoring_v1_engine.py`: fixed weighted scorecard schema and scoring engine.
- `lang/java/calculator.py`: total entropy and derived health score calculation.
- `models/__init__.py`: shared dataclasses (`ProjectFact`, `CodeEntropySignal`, `RawFacts`, `NormalizedInputs`, `ScoredSnapshot`).

## Architecture Snapshot
- `__main__.py` delegates to `cli.main`, so `python -m entropy_audit` and `python -m entropy_audit.cli` share the same CLI path.
- `cli.collect` loads `entropy.config.toml`, collects code entropy facts, and writes `raw_facts.json` plus `normalized_inputs.json`.
- `cli.score` packages normalized project facts into `metrics.json` and rewrites the compact `code_entropy_export.json`.
- `cli.report` renders `entropy-dashboard.html`, `code_entropy_details.json`, and per-dimension files under `code-entropy-details/`.
- `cli.run` executes collect, score, and report in sequence.
- `collectors/code_entropy_collector.py` prefers a configured `sources.code_entropy_export` when present; otherwise it runs internal analysis through the language adapter.
- `lang/java/runner.py` discovers Java files, builds monitor config from TOML, detects project profile, runs five analyzers, applies scoring v1 metadata, and builds export payloads.
- `reporter/html_dashboard.py` is the large UI/report surface. Generated HTML/JSON should come from this code and report inputs, not manual edits.

## Java Entropy Dimensions
- `structure.py`: directory concentration, shared buckets, oversized directories, duplicate/cycle evidence.
- `semantic.py`: glossary and naming consistency, undefined terms, duplicate state evidence.
- `behavior.py`: return/error/exception consistency evidence.
- `cognition.py`: TODO/FIXME/HACK, Javadoc gaps, large methods, cognitive debt.
- `style.py`: naming, formatting, comment density, style consistency evidence.

## Current Repository Context
- Parent repo is a multi-module Java/Maven backend. Root `pom.xml` and modules include `bpc-base`, `bpc-config`, `bpc-gateway`, `bpc-group`, `bpc-manage`, `bpc-manage-bpm`, and `bpc-operation`.
- `entropy.config.toml` is the single main entropy config. Current project language is `java`; internal package prefix is `com.iwhalecloud.dict`.
- Tests live at `BPC_V2/tests/`, focused on code entropy scoring and dashboard-only rendering.
- Root `AGENTS.md` says non-trivial work should create an execution plan under `docs/exec-plans/` before editing code.

## Working Directory
- Prefer running CLI commands from the parent `BPC_V2` directory, not from inside `entropy_audit`, so `python -m entropy_audit.cli` imports correctly.
- Current package root is `BPC_V2/entropy_audit`.
- Project config files live one level up: `BPC_V2/entropy.config.toml` and `BPC_V2/entropy.calibration.toml`.

## Main Commands
- Run commands from `BPC_V2`, not `BPC_V2/entropy_audit`.
- Full monthly pipeline:
  `python -m entropy_audit.cli run --project-root . --config entropy.config.toml --calibration entropy.calibration.toml --period 2026-04 --mode monthly --out-dir reports/2026-04`
- Collect only:
  `python -m entropy_audit.cli collect --project-root . --config entropy.config.toml --period 2026-04 --out-dir reports/2026-04`
- Score only:
  `python -m entropy_audit.cli score --inputs reports/2026-04/normalized_inputs.json --config entropy.config.toml --calibration entropy.calibration.toml --out-dir reports/2026-04`
- Render reports only:
  `python -m entropy_audit.cli report --metrics reports/2026-04/metrics.json --period 2026-04 --mode monthly --out-dir reports/2026-04`
- Syntax check:
  `python -m compileall entropy_audit`
- All Python tests:
  `python -m unittest discover -s tests -p "test*.py"`
- Focused tests:
  `python -m unittest tests.test_code_entropy_scoring_v1`
  `python -m unittest tests.test_code_entropy_dashboard_only`

## Generated Outputs
- `reports/<period>/raw_facts.json`: raw collected facts.
- `reports/<period>/normalized_inputs.json`: normalized metric inputs.
- `reports/<period>/metrics.json`: scored snapshot.
- `reports/<period>/monthly-entropy-report.md`: monthly Markdown report.
- `reports/<period>/entropy-dashboard.html`: main HTML dashboard.
- `reports/<period>/code_entropy_export.json`: compact code entropy export.
- `reports/<period>/code_entropy_details.json`: complete code entropy detail export.
- `reports/<period>/code-entropy-details/*.html`: independent detail pages for structure, semantic, behavior, cognition, and style entropy.
- `reports/<period>/code-entropy-details/*.json`: per-entropy JSON exports.

## Code Entropy UI Rules
- The main dashboard should stay summary-focused.
- Each code entropy card should support quick preview, complete detail page, and JSON export.
- Quick preview belongs in a right-side drawer.
- Large detail data belongs in independent detail pages with search, pagination, sorting, and export.
- Circular dependency groups are part of structure entropy, not a separate top-level entropy category.
- Code entropy scores are entropy values: lower is better, higher means higher risk.
- Health score is separate: higher is better.

## Implementation Rules
- For non-trivial code changes, create/update an execution plan under `docs/exec-plans/` before editing.
- Keep old external tool behavior absorbed into `entropy_audit`; do not hard-code paths to local historical tools.
- Prefer adding analyzers under `lang/<language>/analyzers/` and routing through the language adapter.
- Keep report generation deterministic from `metrics.json` plus any detail JSON in the same report directory.
- Preserve existing JSON output names because the dashboard and reports link to them.
- Avoid editing generated report files by hand; update reporter code and regenerate outputs.
- Do not delete or rewrite unrelated project files when working on this package.
- When changing scoring policy, expect golden tests and scorecard hash assertions to need intentional updates.
- When changing dashboard copy/layout, keep dashboard summary-focused and keep large detail data in independent detail pages.

## Verification
- After code changes, run `python -m compileall entropy_audit` from `BPC_V2`.
- For dashboard/report changes, regenerate the target report with the `report` command.
- For collector/analyzer changes, run the full `run` pipeline so raw facts, normalized inputs, metrics, and reports stay aligned.
- Browser-check `reports/<period>/entropy-dashboard.html` and at least one detail page when HTML or JavaScript changes.
