# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working directory

Run package commands from parent `BPC_V2` directory, not from inside `entropy_audit`, so `python -m entropy_audit.cli` imports package correctly.

Project configuration lives one level above package:
- `entropy.config.toml`
- `entropy.calibration.toml`

## Commands

Full pipeline:

```bash
python -m entropy_audit.cli run --project-root . --config entropy.config.toml --calibration entropy.calibration.toml --period 2026-04 --mode monthly --out-dir reports/2026-04
```

Collect code entropy facts only:

```bash
python -m entropy_audit.cli collect --project-root . --config entropy.config.toml --period 2026-04 --out-dir reports/2026-04
```

Score normalized inputs:

```bash
python -m entropy_audit.cli score --inputs reports/2026-04/normalized_inputs.json --config entropy.config.toml --calibration entropy.calibration.toml --out-dir reports/2026-04
```

Render dashboard and detail exports:

```bash
python -m entropy_audit.cli report --metrics reports/2026-04/metrics.json --period 2026-04 --mode monthly --out-dir reports/2026-04
```

Syntax check:

```bash
python -m compileall entropy_audit
```

Run all Python tests:

```bash
python -m unittest discover -s tests -p "test*.py"
```

Run focused code entropy tests:

```bash
python -m unittest tests.test_code_entropy_scoring_v1
python -m unittest tests.test_code_entropy_dashboard_only
```

Run one test case:

```bash
python -m unittest tests.test_code_entropy_scoring_v1.CodeEntropyScoringV1GoldenTest.test_v1_golden_scores_for_five_dimensions
```

## CLI structure

`cli.py` exposes five subcommands:
- `init`: create project config/calibration files.
- `collect`: collect code entropy facts from internal Java analyzers or optional `code_entropy_export.json`.
- `score`: package normalized code entropy project facts into `metrics.json` and rewrite `code_entropy_export.json`.
- `report`: render `entropy-dashboard.html`, `code_entropy_details.json`, and `code-entropy-details/*.html/*.json`.
- `run`: execute collect, score, and report in one pipeline.

`__main__.py` delegates to `cli.main`, so module execution uses same entry point.

## Architecture

`config.py` reads `entropy.config.toml` into `ProjectConfig`. Raw TOML remains on `config.raw` because Java entropy scoring config is schema-validated in language adapter code.

`collectors/code_entropy_collector.py` is the active collector. It loads configured `sources.code_entropy_export` when present; otherwise it runs internal Java code entropy analysis and stores five entropy signals plus summary/detail/meta payloads.

`lang/` is language adapter layer. Java is active implementation. `lang/java/runner.py` orchestrates Java file discovery, project profile detection, five entropy analyzers, scoring v1 config, detail export config, and summary health metadata.

`lang/java/analyzers/` contains five code-native entropy analyzers:
- `structure.py`: shared buckets, directories, oversized directories, concentration, duplicate/cycle evidence.
- `semantic.py`: glossary, term variants, undefined terms, duplicate states, semantic naming evidence.
- `behavior.py`: return/error/exception consistency evidence.
- `cognition.py`: TODO/FIXME/HACK, Javadoc gaps, large methods, cognitive debt evidence.
- `style.py`: naming, formatting, comment-density, and style consistency evidence.

`lang/java/scoring_v1_schema.py` and `lang/java/scoring_v1_engine.py` implement fixed weighted code entropy scorecards. Golden tests assert five-dimension scores, partial coverage behavior, and scorecard hash changes.

`lang/java/calculator.py` calculates total entropy and derived health score from five dimension scores. Health formula is `100 - total_entropy_score` per `[code_entropy.score_models.health]`.

`reporter/html_dashboard.py` renders code entropy dashboard homepage, side drawer templates, five detail pages, and five JSON detail exports. Generated report files should be regenerated from code and input JSON, not edited manually.

`models/__init__.py` defines current shared dataclasses: `ProjectFact`, `CodeEntropySignal`, `RawFacts`, `NormalizedInputs`, and `ScoredSnapshot`.

## Generated outputs

Pipeline outputs are written under `reports/<period>/`:
- `raw_facts.json`
- `normalized_inputs.json`
- `metrics.json`
- `entropy-dashboard.html`
- `code_entropy_export.json`
- `code_entropy_details.json`
- `code-entropy-details/structure.html`
- `code-entropy-details/semantic.html`
- `code-entropy-details/behavior.html`
- `code-entropy-details/cognition.html`
- `code-entropy-details/style.html`
- `code-entropy-details/*.json`

## Project rules from AGENTS.md

For non-trivial changes, create a plan under `docs/exec-plans/` before editing code.

Keep old external code-entropy tool behavior absorbed into `entropy_audit`; do not hard-code paths to historical local tools.

Prefer adding language behavior through `lang/<language>/` adapters/analyzers instead of branching throughout CLI.

Preserve existing JSON output names because dashboard and reports link to them.

For dashboard/report changes, regenerate target report and browser-check `reports/<period>/entropy-dashboard.html` plus at least one detail page when browser tooling is available.
