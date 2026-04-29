# CODEX.md

这份文件是给 Codex / OpenAI 编码代理的项目初始化说明。以后在处理 `entropy_audit` 相关任务时，优先阅读本文件和同目录的 `AGENTS.md`，可避免重复熟悉项目。

## 工作目录

- 仓库根目录：`D:\iwhaleCloud\GIT_IDEA_PROJECT\BPC_V2_2026\BPC_V2`
- Python 包目录：`entropy_audit`
- 执行命令时通常应站在 `BPC_V2` 根目录，而不是 `entropy_audit` 内部。
- 主配置文件在包目录上一层：`entropy.config.toml`、`entropy.calibration.toml`。

## 项目定位

- `entropy_audit` 是代码熵治理审计工具，用于采集事实、归一化指标、评分并生成月度/季度报表。
- 当前核心能力是 Java 多模块后端项目的代码熵分析。
- 代码熵分析已内置在本包内，不应依赖旧的外部本地工具路径。
- 报表输出应由 `metrics.json` 和同目录明细 JSON 驱动，不要手工修改生成后的报表文件。

## 核心入口

- `entropy_audit/cli.py`：命令入口，包含 `init`、`collect`、`score`、`report`、`run`。
- `entropy_audit/__main__.py`：委托给 `cli.main`，支持 `python -m entropy_audit`。
- `entropy_audit/config.py`：读取 `entropy.config.toml`。
- `entropy_audit/calibration.py`：读取评分校准配置。
- `entropy_audit/collectors/code_entropy_collector.py`：代码熵采集器；优先读取配置的导出文件，否则运行内置 Java 分析。
- `entropy_audit/lang/java/runner.py`：Java 分析编排，负责文件发现、项目画像、五类熵分析、评分元数据与导出 payload。
- `entropy_audit/reporter/html_dashboard.py`：HTML 仪表盘和代码熵详情页渲染主文件。

## Java 代码熵模块

- `entropy_audit/lang/java/analyzers/structure.py`：结构熵，目录集中度、共享桶、超大目录、重复/循环依赖证据。
- `entropy_audit/lang/java/analyzers/semantic.py`：语义熵，术语表、命名一致性、未定义术语、重复状态证据。
- `entropy_audit/lang/java/analyzers/behavior.py`：行为熵，返回值、错误码、异常一致性证据。
- `entropy_audit/lang/java/analyzers/cognition.py`：认知熵，TODO/FIXME/HACK、Javadoc 缺口、大方法、认知债务。
- `entropy_audit/lang/java/analyzers/style.py`：风格熵，命名、格式、注释密度、风格一致性证据。
- `entropy_audit/lang/java/scoring_v1_schema.py`：v1 固定权重评分卡 schema。
- `entropy_audit/lang/java/scoring_v1_engine.py`：v1 评分引擎。
- `entropy_audit/lang/java/calculator.py`：总熵与健康分计算。
- `entropy_audit/lang/java/details.py`：明细导出结构构建。

## 常用命令

从 `BPC_V2` 根目录执行：

```powershell
python -m entropy_audit.cli run --project-root . --config entropy.config.toml --calibration entropy.calibration.toml --period 2026-04 --mode monthly --out-dir reports/2026-04
```

```powershell
python -m entropy_audit.cli collect --project-root . --config entropy.config.toml --period 2026-04 --out-dir reports/2026-04
```

```powershell
python -m entropy_audit.cli score --inputs reports/2026-04/normalized_inputs.json --config entropy.config.toml --calibration entropy.calibration.toml --out-dir reports/2026-04
```

```powershell
python -m entropy_audit.cli report --metrics reports/2026-04/metrics.json --period 2026-04 --mode monthly --out-dir reports/2026-04
```

```powershell
python -m compileall entropy_audit
python -m unittest discover -s tests -p "test*.py"
python -m unittest tests.test_code_entropy_scoring_v1
python -m unittest tests.test_code_entropy_dashboard_only
```

## 输出文件

- `reports/<period>/raw_facts.json`：采集到的原始事实。
- `reports/<period>/normalized_inputs.json`：归一化输入。
- `reports/<period>/metrics.json`：评分快照。
- `reports/<period>/monthly-entropy-report.md`：月度 Markdown 报告。
- `reports/<period>/entropy-dashboard.html`：主仪表盘。
- `reports/<period>/code_entropy_export.json`：精简代码熵导出。
- `reports/<period>/code_entropy_details.json`：完整代码熵明细导出。
- `reports/<period>/code-entropy-details/*.html`：结构、语义、行为、认知、风格熵独立详情页。
- `reports/<period>/code-entropy-details/*.json`：各维度详情 JSON。

## 修改规则

- 非平凡代码修改前，按项目约定在 `docs/exec-plans/` 下建立或更新执行计划。
- 修改分析逻辑时，优先在 `lang/<language>/analyzers/` 增强，并通过语言适配层接入。
- 修改评分策略时，要预期 golden tests 和 scorecard hash 断言需要同步更新。
- 修改仪表盘文案或布局时，主仪表盘保持摘要化，大量明细放在独立详情页。
- 不要手工编辑 `reports/` 下生成的 HTML/JSON；应改 reporter 或输入数据后重新生成。
- 保持现有 JSON 文件名稳定，因为仪表盘和详情页依赖这些链接。
- 不要删除或重写无关文件。

## 验证建议

- 改 Python 代码后：`python -m compileall entropy_audit`。
- 改 collector/analyzer 后：运行完整 `run` pipeline，确保 raw facts、normalized inputs、metrics、reports 一致。
- 改 dashboard/report 后：运行 `report` 命令重新生成目标报告。
- 改 HTML/JavaScript 后：浏览器检查 `reports/<period>/entropy-dashboard.html` 和至少一个详情页。

## 快速接手提示

- 如果用户只说“熟悉 entropy_audit”，先读 `entropy_audit/AGENTS.md`、本文件、`entropy.config.toml`、`tests/test_code_entropy_scoring_v1.py`。
- 如果任务涉及语义熵，优先看 `entropy_audit/lang/java/analyzers/semantic.py`、`glossary.md`、`entropy.config.toml` 中 `[code_entropy.java.detectors.semantic]` 相关配置。
- 如果任务涉及详情页或抽屉 UI，优先看 `entropy_audit/reporter/html_dashboard.py` 中 `render_html_dashboard`、`build_code_entropy_detail_exports`、`render_code_entropy_detail_pages`。
- 如果任务涉及评分差异，优先看 `entropy_audit/lang/java/scoring_v1_schema.py`、`entropy_audit/lang/java/scoring_v1_engine.py` 和 `tests/test_code_entropy_scoring_v1.py`。
