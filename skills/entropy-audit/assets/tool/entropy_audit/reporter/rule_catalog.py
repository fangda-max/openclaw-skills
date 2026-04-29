from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from entropy_audit.lang.java.scoring_v1_schema import build_scoring_v1


DIMENSION_SCOPES = {
    "structure": "目录边界、共享承载、目录分布与目录粒度。",
    "semantic": "术语一致、命名漂移、状态承载体重复与状态值散落。",
    "behavior": "失败路径、异常语义、错误返回契约与业务异常收敛。",
    "cognition": "技术债、公共知识缺口、复杂方法、大文件与项目文档。",
    "style": "Checkstyle 规范、坏味道与复杂度。",
}

STATUS_LABELS = {
    "danger": "危险",
    "warning": "预警",
    "notice": "关注",
    "pass": "通过",
    "missing": "缺数",
    "scored": "计分",
    "disabled": "停用",
    "experimental": "实验",
}

CATEGORY_LABELS = {
    "custom": "项目定制",
    "general": "通用规则",
}

DIRECTION_LABELS = {
    "higher_is_worse": "越高风险越大",
    "lower_is_worse": "越低风险越大",
}

UNIT_LABELS = {
    "ratio": "比例",
    "files_per_dir": "每目录文件数",
    "count_per_k_files": "每千文件数量",
    "issues_per_kloc": "每千行问题数",
}

MISSING_LABELS = {
    "zero": "缺失按 0 处理",
    "null": "缺失标记为空值",
}

WEIGHT_KEYS = {
    "structure": "structure_entropy",
    "semantic": "semantic_entropy",
    "behavior": "behavior_entropy",
    "cognition": "cognition_entropy",
    "style": "style_entropy",
}


def render_rule_catalog(config_payload: dict[str, Any], *, source_path: Path | None = None) -> str:
    scoring = _load_scoring(config_payload, source_path=source_path)
    code_entropy = config_payload.get("code_entropy", {}) if isinstance(config_payload.get("code_entropy"), dict) else {}
    weights = code_entropy.get("weights", {}) if isinstance(code_entropy.get("weights"), dict) else {}
    dimensions = scoring.get("dimensions", {}) if isinstance(scoring.get("dimensions"), dict) else {}
    dimension_order = [
        name
        for name in scoring.get("migrated_dimensions", [])
        if isinstance(name, str) and isinstance(dimensions.get(name), dict)
    ]
    catalog = _build_catalog_model(dimension_order, dimensions, weights)
    nav_html = "\n".join(_render_nav_dimension(item) for item in catalog["dimensions"])
    overview_html = "\n".join(_render_overview_card(item) for item in catalog["dimensions"])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>规则目录</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg:#09111b; --surface:#0f1a29; --surface-alt:#132132; --surface-raised:rgba(15,26,41,.88);
      --surface-glass:rgba(255,255,255,.06); --strong:#08111d; --strong-2:#0d1c2d;
      --text:#e8eef6; --muted:#9fb0c2; --line:#24364a; --line-strong:#36506b;
      --brand:#0f766e; --brand-ink:#0b5b55; --brand-soft:rgba(15,118,110,.18);
      --good:#15803d; --good-soft:rgba(21,128,61,.2); --warning:#b76e12; --warning-soft:rgba(183,110,18,.2);
      --danger:#c2410c; --danger-soft:rgba(194,65,12,.22); --focus:#38bdf8;
      --radius-md:18px; --radius-lg:28px; --shadow-sm:0 14px 30px rgba(0,0,0,.28);
      --shadow-md:0 26px 56px rgba(0,0,0,.38);
    }}
    * {{ box-sizing:border-box; }}
    html {{ min-height:100%; scroll-behavior:smooth; background:var(--bg); }}
    body {{
      margin:0;
      min-height:100vh;
      font-family:"Avenir Next","Segoe UI Variable","Segoe UI","PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15,118,110,.16), transparent 24%),
        radial-gradient(circle at 88% 0, rgba(37,99,235,.12), transparent 20%),
        linear-gradient(180deg, rgba(255,255,255,.18), transparent 22%),
        var(--bg);
      background-repeat:no-repeat;
      background-attachment:fixed;
      color:var(--text);
      line-height:1.6;
      font-size:15px;
    }}
    button, input {{ font:inherit; }}
    button {{ cursor:pointer; }}
    button:focus-visible, input:focus-visible {{ outline:3px solid var(--focus); outline-offset:3px; }}
    .shell {{ max-width:1500px; min-height:100vh; margin:0 auto; padding:26px 24px 36px; }}
    .hero {{ padding:18px 0 16px; }}
    .eyebrow {{ color:var(--brand); font-size:13px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }}
    h1 {{ margin:4px 0 0; font-size:clamp(30px,4vw,46px); line-height:1.05; letter-spacing:0; }}
    h2, h3, p {{ margin:0; }}
    .hero p {{ margin-top:12px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .score-pill {{
      display:inline-flex; align-items:center; justify-content:center; min-height:34px; padding:0 12px;
      border:1px solid rgba(15,118,110,.28); border-radius:999px; color:#99f6e4; background:var(--brand-soft);
      font-size:12px; font-weight:800; white-space:nowrap;
    }}
    .workbench {{ display:grid; grid-template-columns:330px minmax(0,1fr); gap:20px; margin-top:20px; align-items:start; }}
    .sidebar {{
      position:sticky; top:18px; max-height:calc(100vh - 36px); overflow:auto; scrollbar-width:thin;
      border:1px solid var(--line); border-radius:var(--radius-lg);
      background:linear-gradient(180deg,var(--surface-raised),var(--surface));
      box-shadow:var(--shadow-sm);
    }}
    .side-head {{ padding:18px; border-bottom:1px solid var(--line); background:var(--surface-alt); }}
    .side-title {{ color:var(--text); font-size:16px; font-weight:800; }}
    .side-help {{ margin-top:6px; color:var(--muted); font-size:12px; line-height:1.5; }}
    .search {{
      width:100%; min-height:44px; margin-top:14px; padding:0 13px; border:1px solid var(--line);
      border-radius:14px; color:var(--text); background:var(--strong);
    }}
    .search::placeholder {{ color:rgba(159,176,194,.72); }}
    .tree {{ padding:10px; display:grid; gap:8px; }}
    .tree-group {{ border:1px solid transparent; border-radius:16px; overflow:hidden; }}
    .tree-group.active {{ border-color:rgba(15,118,110,.42); background:var(--brand-soft); }}
    .tree-group.collapsed .rule-list {{ display:none; }}
    .dimension-btn {{
      width:100%; min-height:52px; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:8px;
      padding:10px 12px; border:0; background:transparent; color:var(--text); text-align:left;
    }}
    .dimension-main {{ display:flex; align-items:center; gap:8px; min-width:0; }}
    .chevron {{
      width:18px; height:18px; display:inline-flex; align-items:center; justify-content:center; flex:none;
      color:var(--muted); transition:transform .18s ease;
    }}
    .tree-group.collapsed .chevron {{ transform:rotate(-90deg); }}
    .dimension-copy {{ min-width:0; }}
    .dimension-name {{ font-size:15px; font-weight:800; }}
    .dimension-key {{ color:var(--muted); font-size:12px; font-weight:700; }}
    .rule-count {{ color:#99f6e4; font-size:12px; font-weight:800; white-space:nowrap; }}
    .rule-list {{ display:grid; gap:4px; padding:0 8px 10px 18px; }}
    .rule-btn {{
      width:100%; min-height:42px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; align-items:center;
      border:1px solid transparent; border-radius:12px; padding:7px 9px; color:var(--muted); background:transparent; text-align:left;
    }}
    .rule-btn:hover, .rule-btn.active {{ color:var(--text); background:var(--surface-alt); border-color:var(--line); }}
    .rule-btn.active {{ border-color:var(--brand); box-shadow:inset 3px 0 0 var(--brand); }}
    .rule-label {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; font-weight:700; }}
    .rule-weight-mini {{ color:#f7c46e; font-size:12px; font-weight:800; font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .content {{ display:grid; gap:18px; min-width:0; align-content:start; }}
    .overview-grid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-top:10px; }}
    .overview-card {{
      min-width:0; min-height:118px; padding:16px; border:1px solid var(--line); border-radius:20px;
      background:linear-gradient(180deg,var(--surface-alt),var(--surface)); box-shadow:var(--shadow-sm);
    }}
    .overview-card.active {{ border-color:rgba(15,118,110,.62); box-shadow:0 0 0 1px rgba(15,118,110,.25), var(--shadow-sm); }}
    .overview-top {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }}
    .overview-name {{ font-weight:800; }}
    .overview-key {{ color:var(--muted); font-size:12px; font-weight:700; }}
    .overview-scope {{ min-height:42px; margin-top:8px; color:var(--muted); font-size:13px; line-height:1.55; }}
    .overview-stats {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:12px; }}
    .stat {{ min-width:0; padding:9px 10px; border:1px solid var(--line); border-radius:14px; background:rgba(255,255,255,.04); }}
    .stat span {{ display:block; color:var(--muted); font-size:11px; font-weight:700; }}
    .stat strong {{ display:block; margin-top:2px; color:var(--text); font-size:14px; font-weight:800; }}
    .detail-shell {{
      min-height:560px;
      border:1px solid var(--line); border-radius:var(--radius-lg);
      background:linear-gradient(180deg,var(--surface-raised),var(--surface)); box-shadow:var(--shadow-sm);
      overflow:hidden;
    }}
    .detail-top {{
      display:grid; grid-template-columns:minmax(0,1fr) auto; gap:20px; align-items:start;
      padding:22px 24px; border-bottom:1px solid var(--line); background:linear-gradient(145deg,var(--strong),var(--strong-2));
    }}
    .detail-kicker {{ color:var(--brand); font-size:13px; font-weight:800; }}
    .detail-title {{ margin-top:4px; color:#fff; font-size:28px; line-height:1.18; font-weight:800; }}
    .detail-summary {{ max-width:82ch; margin-top:10px; color:rgba(232,238,246,.78); }}
    .rule-id {{ color:var(--muted); font-family:Consolas,"Courier New",monospace; font-size:13px; overflow-wrap:anywhere; }}
    .weight-panel {{ min-width:210px; padding:14px 16px; border:1px solid rgba(255,255,255,.12); border-radius:18px; background:rgba(255,255,255,.07); }}
    .weight-panel span {{ display:block; color:rgba(232,238,246,.64); font-size:12px; font-weight:800; }}
    .weight-panel strong {{ display:block; margin-top:4px; color:#fbd38d; font-size:26px; line-height:1; font-weight:800; font-variant-numeric:tabular-nums; }}
    .weight-panel p {{ margin:8px 0 0; color:rgba(232,238,246,.66); font-size:12px; line-height:1.45; }}
    .guide-strip {{
      grid-column:1 / -1;
      display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px;
      padding:18px; border-bottom:1px solid var(--line); background:rgba(255,255,255,.025);
    }}
    .guide-card {{ min-width:0; min-height:132px; padding:14px; border:1px solid var(--line); border-radius:16px; background:rgba(255,255,255,.04); }}
    .guide-card span {{ display:block; color:#99f6e4; font-size:12px; font-weight:800; }}
    .guide-card p {{ margin-top:8px; color:var(--text); font-size:13px; line-height:1.55; }}
    .detail-grid {{ display:grid; grid-template-columns:minmax(320px,.82fr) minmax(420px,1.18fr); gap:1px; background:var(--line); }}
    .panel {{ min-width:0; padding:20px; background:var(--surface); }}
    .panel-title {{ color:var(--text); font-size:15px; font-weight:800; }}
    .fields {{ display:grid; gap:12px; margin-top:14px; }}
    .field {{ display:grid; gap:5px; }}
    .field-label {{ color:var(--muted); font-size:12px; font-weight:800; }}
    .field-value {{ color:var(--text); overflow-wrap:anywhere; }}
    .code {{
      display:block; padding:10px 12px; border:1px solid var(--line); border-radius:14px;
      background:var(--strong); color:#d7e2ef; font-family:Consolas,"Courier New",monospace; overflow-wrap:anywhere;
    }}
    .bands-panel {{ grid-column:1 / -1; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; margin-top:14px; }}
    th, td {{ padding:10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
    th {{ color:var(--muted); font-size:12px; font-weight:800; background:var(--surface-alt); }}
    tr:last-child td {{ border-bottom:0; }}
    .status-danger {{ color:#ff8d78; font-weight:800; }}
    .status-warning {{ color:#f7c46e; font-weight:800; }}
    .status-notice {{ color:#99f6e4; font-weight:800; }}
    .empty {{ padding:28px; color:var(--muted); text-align:center; }}
    .hidden {{ display:none !important; }}
    @media (max-width:1180px) {{
      .workbench {{ grid-template-columns:1fr; }}
      .sidebar {{ position:relative; top:auto; max-height:none; }}
      .overview-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .guide-strip {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    }}
    @media (max-width:760px) {{
      .shell {{ padding:18px 14px 30px; }}
      .hero, .detail-top, .detail-grid {{ grid-template-columns:1fr; }}
      .hero p {{ white-space:normal; overflow:visible; text-overflow:clip; }}
      .overview-grid {{ grid-template-columns:1fr; }}
      .guide-strip {{ grid-template-columns:1fr; }}
      .weight-panel {{ min-width:0; }}
      table {{ table-layout:auto; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">Code Entropy Scorecard</div>
        <h1>规则目录</h1>
        <p>左侧按五大熵与规则组织目录，右侧查看当前规则的权重、指标公式、缺数策略和阈值档位；熵分越高代表风险越大。</p>
      </div>
    </section>

    <section class="overview-grid" id="overview-grid" aria-label="五类熵概览">
      {overview_html}
    </section>

    <section class="workbench" aria-label="规则目录工作台">
      <aside class="sidebar">
        <div class="side-head">
          <div class="side-title">五大熵规则目录</div>
          <div class="side-help">点击一级熵类可展开或收起规则；规则右侧数字表示该规则在当前熵类评分中的权重。</div>
          <input id="search" class="search" type="search" placeholder="搜索规则、指标、公式" aria-label="搜索规则、指标、公式">
        </div>
        <nav class="tree" id="rule-tree" aria-label="五大熵与规则导航">
          {nav_html}
        </nav>
      </aside>

      <section class="content">
        <article class="detail-shell" id="rule-detail" aria-live="polite"></article>
      </section>
    </section>
  </main>
  <script>
    const RULE_CATALOG = {json.dumps(catalog, ensure_ascii=False)};
    let selectedRuleId = RULE_CATALOG.dimensions[0]?.rules[0]?.id || '';

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function statusLabel(value) {{ return RULE_CATALOG.labels.status[value] || value || '-'; }}
    function categoryLabel(value) {{ return RULE_CATALOG.labels.category[value] || value || '-'; }}
    function directionLabel(value) {{ return RULE_CATALOG.labels.direction[value] || value || '-'; }}
    function unitLabel(value) {{ return RULE_CATALOG.labels.unit[value] || value || '-'; }}
    function missingLabel(value) {{ return RULE_CATALOG.labels.missing[value] || value || '-'; }}
    function numberText(value) {{ return value === null || value === undefined || value === '' ? '-' : String(value); }}
    const FORMULA_LABELS = {{
      shared_bucket_ratio: '共享承载目录文件数 / Java 文件总数',
      max_dir_files_ratio: '最大目录文件数 / Java 文件总数',
      oversized_dir_ratio: '超大目录数量 / 目录总数',
      top_n_dir_concentration: '前 N 大目录文件数合计 / Java 文件总数',
      avg_files_per_dir: 'Java 文件总数 / 目录总数',
      naming_inconsistency_ratio: '非标准命名命中次数 / 术语家族命名总命中次数',
      term_gap_ratio: '未进入术语表的候选术语数 / 高频候选术语总数',
      state_duplicate_ratio: '重复状态承载体数量 / 状态承载体总数',
      state_value_scatter_ratio: '硬编码状态值次数 / 状态值引用总量',
      failure_strategy_split_ratio: '1 - 主流失败处理策略次数 / 失败处理策略总次数',
      swallowed_exception_ratio: '吞异常 catch 数 / catch 总数',
      error_return_contract_mix_ratio: '1 - 主流错误返回契约次数 / 错误返回契约总次数',
      generic_exception_throw_ratio: '泛化异常抛出次数 / 异常抛出总次数',
      business_exception_convergence_gap: '非标准业务异常抛出次数 / 业务异常抛出总次数',
      todo_density_per_k_files: '债务标记数量 * 1000 / Java 文件总数',
      unowned_debt_ratio: '未归属债务标记数量 / 债务标记总数',
      public_knowledge_gap_ratio: '1 - 已有说明的公共知识数量 / 应说明的公共知识总数',
      complex_method_ratio: '复杂方法数量 / 方法总数',
      large_file_class_burden_ratio: '大文件或大类数量 / Java 文件总数',
      project_doc_gap_ratio: '1 - 项目文档可用度',
      style_formatting_density: '格式排版问题数 / Java 千行代码',
      style_naming_density: '命名规范问题数 / Java 千行代码',
      style_import_density: '导入规范问题数 / Java 千行代码',
      style_declaration_density: '注解与声明规范问题数 / Java 千行代码',
      style_code_smell_density: '编码坏味道问题数 / Java 千行代码',
      style_complexity_density: '复杂度与规模问题数 / Java 千行代码'
    }};
    function formulaLabel(rule, metric) {{
      return FORMULA_LABELS[rule.metric] || metric.formula_cn || metric.formula || rule.metric || '-';
    }}
    const METRIC_GUIDES = {{
      shared_bucket_ratio: {{what:'看有多少 Java 文件落在 common、util、shared 等共享承载目录，用来判断业务代码是否持续往公共目录聚集。', example:'例如全仓 5614 个 Java 文件，共享承载目录里有 359 个，比例 = 359 / 5614 = 6.39%。比例越高，说明边界越容易被 common/util 吞掉。'}},
      max_dir_files_ratio: {{what:'看最大单个目录直接承载了多少 Java 文件，用来定位是否出现超级目录。', example:'例如全仓 5614 个 Java 文件，最大目录有 76 个，比例 = 76 / 5614 = 1.35%。如果命中阈值，优先拆分这个最大目录。'}},
      oversized_dir_ratio: {{what:'看超过大目录阈值的目录有多少个，用来判断目录膨胀是否已经多点扩散。', example:'例如共有 798 个目录，其中 65 个目录超过 20 个文件，比例 = 65 / 798 = 8.15%。比例越高，说明不是单点问题。'}},
      top_n_dir_concentration: {{what:'看前 N 大目录合计吃掉多少文件，用来判断代码是否被少数目录长期垄断。', example:'例如前 5 大目录合计 364 个文件，全仓 5614 个文件，集中度 = 364 / 5614 = 6.48%。'}},
      avg_files_per_dir: {{what:'看每个目录平均承载多少 Java 文件，用来判断目录粒度是否整体偏粗。', example:'例如全仓 5614 个 Java 文件、798 个目录，平均 = 5614 / 798 = 7.04 个文件/目录。'}},
      naming_inconsistency_ratio: {{what:'看同一个业务术语是否出现多套命名变体，用来发现命名漂移。', example:'例如某术语命中 275 次，其中非标准命名 50 次，比例 = 50 / 275 = 18.18%。'}},
      term_gap_ratio: {{what:'看高频候选术语有多少没有进入 glossary 术语表，用来发现项目词典缺口。', example:'例如扫描 50 个高频候选术语，只有 3 个已配置，缺口 = 47 / 50 = 94%。'}},
      state_duplicate_ratio: {{what:'看状态承载体是否重复维护同一批状态项，用来发现状态定义分散。', example:'例如发现 2 组重复状态承载体，状态项总数 149，重复风险会按规则折算为状态承载体重复比。'}},
      state_value_scatter_ratio: {{what:'看硬编码状态值是否散落在 service、controller、mapper 等代码里，而不是收敛到统一状态源。', example:'例如状态承载体定义了 149 个状态项，代码中另有 37 处硬编码状态参与计分，散落比例按这些来源合并计算。'}},
      failure_strategy_split_ratio: {{what:'看 catch 后失败处理策略是否分裂，比如重新抛业务异常、吞掉、返回 null、只打日志等混用。', example:'例如 catch 总数 2627，其中主流策略命中 1056，分裂比例 = 1 - 1056 / 2627 = 59.80%。'}},
      swallowed_exception_ratio: {{what:'看异常是否被 catch 后吞掉，没有继续抛出、返回错误或包装处理。', example:'例如 2627 个 catch 中有 1121 个属于吞异常，比例 = 1121 / 2627 = 42.67%。'}},
      error_return_contract_mix_ratio: {{what:'看 Controller/API 失败时是否混用 ResultVO.error、null、String、Boolean、裸对象等错误返回契约。', example:'例如错误返回点 309 个，其中 226 个符合主契约，混用比例 = 1 - 226 / 309 = 26.86%。'}},
      generic_exception_throw_ratio: {{what:'看是否大量抛 RuntimeException、Exception、Throwable 这类泛化异常，缺少业务语义。', example:'例如 throw 总数 1568，其中泛化异常 226 个，比例 = 226 / 1568 = 14.41%。'}},
      business_exception_convergence_gap: {{what:'看业务异常是否收敛到配置里的标准业务异常集合。', example:'例如业务异常抛出 1206 次，其中 331 次未命中标准异常集合，缺口 = 331 / 1206 = 27.45%。'}},
      todo_density_per_k_files: {{what:'看 TODO、FIXME、HACK 等债务标记密度，用每千文件口径避免大项目天然数量更高。', example:'例如全仓 5614 个文件，债务标记 115 个，密度 = 115 * 1000 / 5614 = 20.49 个/千文件。'}},
      unowned_debt_ratio: {{what:'看已标出的技术债是否有责任人，避免债务长期没人收口。', example:'例如 115 个债务标记里 0 个命中责任人识别规则，未归属比例 = 115 / 115 = 100%。'}},
      public_knowledge_gap_ratio: {{what:'看 public 类和 public 方法是否缺少 JavaDoc，用来发现公共知识没有沉淀。', example:'例如公共知识目标 13208 个，已有说明 8802 个，缺口 = 1 - 8802 / 13208 = 33.36%。'}},
      complex_method_ratio: {{what:'看方法是否过长、分支过多或嵌套过深，用来定位难读难改的方法。', example:'例如识别到 21256 个方法，其中 1059 个复杂方法，比例 = 1059 / 21256 = 4.98%。'}},
      large_file_class_burden_ratio: {{what:'看物理总行数超过阈值的 Java 文件占比，用来定位沉重大类或大文件。', example:'例如全仓 5614 个 Java 文件，其中 13 个超过 1500 行，比例 = 13 / 5614 = 0.23%。'}},
      project_doc_gap_ratio: {{what:'看 README、docs、readme、wiki 等项目说明是否足够支撑新人理解项目。', example:'例如文档可用度为 100%，项目文档缺口 = 1 - 100% = 0%。'}},
      style_formatting_density: {{what:'看缩进、空白、换行、括号、空块等排版类 Checkstyle 问题密度，判断 formatter 或团队排版约定是否稳定落地。', example:'例如格式排版问题 7 处，Java 千行代码 797.114，密度 = 7 / 797.114 = 0.01 处/千行。'}},
      style_naming_density: {{what:'看类名、方法名、包名、泛型参数、静态变量等命名类 Checkstyle 问题密度，判断命名规范是否稳定。', example:'例如命名规范问题 28 处，Java 千行代码 797.114，密度 = 28 / 797.114 = 0.04 处/千行。'}},
      style_import_density: {{what:'看星号导入、非法导入、冗余导入、未使用导入等导入类 Checkstyle 问题密度，判断依赖引用是否清洁。', example:'例如导入规范问题 1 处，Java 千行代码 797.114，密度 = 1 / 797.114 = 0.00 处/千行。'}},
      style_declaration_density: {{what:'看注解位置、Override、包注解、修饰符顺序、顶层类数量等声明类 Checkstyle 问题密度，判断代码结构入口是否稳定。', example:'例如注解与声明规范问题 44 处，Java 千行代码 797.114，密度 = 44 / 797.114 = 0.06 处/千行。'}},
      style_code_smell_density: {{what:'看空 catch、直接打印、字符串比较、equals/hashCode、控制变量修改等坏味道问题密度，判断维护风险是否扩散。', example:'例如编码坏味道问题 76 处，Java 千行代码 797.114，密度 = 76 / 797.114 = 0.10 处/千行。'}},
      style_complexity_density: {{what:'看文件长度、嵌套深度、布尔表达式复杂度、参数数量等复杂度与规模类 Checkstyle 问题密度，判断理解和修改成本。', example:'例如复杂度与规模问题 22 处，Java 千行代码 797.114，密度 = 22 / 797.114 = 0.03 处/千行。'}}
    }};
    function guideFor(rule, metric) {{
      const guide = METRIC_GUIDES[rule.metric] || {{}};
      const firstBand = (rule.bands || [])[0] || {{}};
      const formula = formulaLabel(rule, metric);
      const abnormal = firstBand.label_cn
        ? `命中“${{firstBand.label_cn}}”时会进入${{statusLabel(firstBand.status)}}档，风险分为 ${{numberText(firstBand.score)}}。未命中任何阈值时按 ${{numberText(rule.score_if_no_match)}} 分处理。`
        : `没有配置阈值档位时，未命中按 ${{numberText(rule.score_if_no_match)}} 分处理。`;
      return {{
        what: guide.what || metric.meaning_cn || rule.rule_cn || '这条规则用于判断当前项目在该维度上的风险信号。',
        calc: `先计算指标“${{metric.label || rule.metric}}”：${{formula}}；再按下方阈值档位换算风险分，最后乘以规则权重计入当前熵类总分。`,
        example: guide.example || `举例：如果分子为 80、分母为 1000，则指标值为 80 / 1000 = 8%；再对照阈值档位决定风险分。`,
        abnormal
      }};
    }}
    function findRule(ruleId) {{
      for (const dimension of RULE_CATALOG.dimensions) {{
        const rule = dimension.rules.find(item => item.id === ruleId);
        if (rule) return {{dimension, rule}};
      }}
      return null;
    }}
    function renderDetail() {{
      const found = findRule(selectedRuleId);
      const target = document.getElementById('rule-detail');
      if (!found) {{
        target.innerHTML = '<div class="empty">没有匹配到规则。</div>';
        return;
      }}
      const {{dimension, rule}} = found;
      const metric = rule.metric_definition || {{}};
      const guide = guideFor(rule, metric);
      const rows = (rule.bands || []).map(band => `
        <tr>
          <td>${{escapeHtml(band.op)}} ${{escapeHtml(numberText(band.value))}}</td>
          <td>${{escapeHtml(numberText(band.score))}}</td>
          <td class="status-${{escapeHtml(band.status)}}">${{escapeHtml(statusLabel(band.status))}}</td>
          <td>${{escapeHtml(band.label_cn)}}</td>
        </tr>
      `).join('');
      target.innerHTML = `
        <div class="detail-top">
          <div>
            <div class="detail-kicker">${{escapeHtml(dimension.label)}} / ${{escapeHtml(dimension.key)}}</div>
            <div class="detail-title">${{escapeHtml(rule.label)}}</div>
            <p class="detail-summary">${{escapeHtml(rule.rule_cn)}}</p>
            <div class="rule-id">${{escapeHtml(rule.id)}}</div>
          </div>
          <div class="weight-panel" title="规则权重：${{escapeHtml(numberText(rule.weight))}}。权重越高，这条规则对当前熵类总分影响越大。">
            <span>规则权重</span>
            <strong>${{escapeHtml(numberText(rule.weight))}}</strong>
            <p>权重越高，这条规则对当前熵类总分影响越大。</p>
          </div>
        </div>
        <div class="detail-grid">
          <section class="guide-strip">
            <article class="guide-card"><span>这条规则看什么</span><p>${{escapeHtml(guide.what)}}</p></article>
            <article class="guide-card"><span>怎么算</span><p>${{escapeHtml(guide.calc)}}</p></article>
            <article class="guide-card"><span>计算例子</span><p>${{escapeHtml(guide.example)}}</p></article>
            <article class="guide-card"><span>什么算异常</span><p>${{escapeHtml(guide.abnormal)}}</p></article>
          </section>
          <section class="panel">
            <h3 class="panel-title">规则属性</h3>
            <div class="fields">
              <div class="field"><div class="field-label">分类 / 状态</div><div class="field-value">${{escapeHtml(categoryLabel(rule.category))}} / ${{escapeHtml(statusLabel(rule.state))}}</div></div>
              <div class="field"><div class="field-label">风险方向</div><div class="field-value">${{escapeHtml(directionLabel(rule.direction))}}</div></div>
              <div class="field"><div class="field-label">未命中阈值档位</div><div class="field-value">${{escapeHtml(numberText(rule.score_if_no_match))}} 分</div></div>
              <div class="field"><div class="field-label">指标缺失兜底</div><div class="field-value">${{escapeHtml(numberText(rule.score_if_missing))}} 分</div></div>
            </div>
          </section>
          <section class="panel">
            <h3 class="panel-title">计算指标</h3>
            <div class="fields">
              <div class="field"><div class="field-label">绑定指标</div><div class="field-value">${{escapeHtml(metric.label || rule.metric)}} <span class="rule-id">${{escapeHtml(rule.metric)}}</span></div></div>
              <div class="field"><div class="field-label">指标公式</div><code class="code" title="配置公式：${{escapeHtml(metric.formula_cn || metric.formula || '')}}">${{escapeHtml(formulaLabel(rule, metric))}}</code></div>
              <div class="field"><div class="field-label">指标含义</div><div class="field-value">${{escapeHtml(metric.meaning_cn)}}</div></div>
              <div class="field"><div class="field-label">单位 / 缺数策略</div><div class="field-value">${{escapeHtml(unitLabel(metric.unit))}} / ${{escapeHtml(missingLabel(metric.when_missing))}}</div></div>
            </div>
          </section>
          <section class="panel bands-panel">
            <h3 class="panel-title">阈值档位</h3>
            <table>
              <thead><tr><th>匹配条件</th><th>风险分</th><th>状态</th><th>说明</th></tr></thead>
              <tbody>${{rows}}</tbody>
            </table>
          </section>
        </div>
      `;
      document.querySelectorAll('.tree-group').forEach(el => el.classList.toggle('active', el.dataset.dimension === dimension.key));
      document.querySelectorAll('.tree-group').forEach(el => el.classList.toggle('collapsed', el.dataset.dimension !== dimension.key && !document.getElementById('search').value.trim()));
      document.querySelectorAll('.dimension-btn').forEach(btn => {{
        const group = btn.closest('.tree-group');
        btn.setAttribute('aria-expanded', group && !group.classList.contains('collapsed') ? 'true' : 'false');
      }});
      document.querySelectorAll('.rule-btn').forEach(el => el.classList.toggle('active', el.dataset.ruleId === rule.id));
      document.querySelectorAll('.overview-card').forEach(el => el.classList.toggle('active', el.dataset.dimension === dimension.key));
    }}
    function selectRule(ruleId) {{
      selectedRuleId = ruleId;
      renderDetail();
    }}
    document.querySelectorAll('.rule-btn').forEach(btn => btn.addEventListener('click', () => selectRule(btn.dataset.ruleId)));
    document.querySelectorAll('.dimension-btn').forEach(btn => btn.addEventListener('click', () => {{
      const group = btn.closest('.tree-group');
      if (group && group.classList.contains('active') && !group.classList.contains('collapsed')) {{
        group.classList.add('collapsed');
        btn.setAttribute('aria-expanded', 'false');
        return;
      }}
      if (group) {{
        group.classList.remove('collapsed');
        btn.setAttribute('aria-expanded', 'true');
      }}
      const dimension = RULE_CATALOG.dimensions.find(item => item.key === btn.dataset.dimension);
      if (dimension?.rules?.[0]) selectRule(dimension.rules[0].id);
    }}));
    document.getElementById('search').addEventListener('input', event => {{
      const query = event.target.value.trim().toLowerCase();
      let firstVisible = '';
      document.querySelectorAll('.rule-btn').forEach(btn => {{
        const hit = !query || btn.dataset.search.toLowerCase().includes(query);
        btn.classList.toggle('hidden', !hit);
        if (hit && !firstVisible) firstVisible = btn.dataset.ruleId;
      }});
      document.querySelectorAll('.tree-group').forEach(group => {{
        const hit = !query || group.dataset.search.toLowerCase().includes(query) || group.querySelectorAll('.rule-btn:not(.hidden)').length > 0;
        group.classList.toggle('hidden', !hit);
        group.classList.toggle('collapsed', !query && !group.classList.contains('active'));
        const btn = group.querySelector('.dimension-btn');
        if (btn) btn.setAttribute('aria-expanded', group.classList.contains('collapsed') ? 'false' : 'true');
      }});
      if (firstVisible) selectRule(firstVisible);
    }});
    renderDetail();
  </script>
</body>
</html>
"""


def _load_scoring(config_payload: dict[str, Any], *, source_path: Path | None) -> dict[str, Any]:
    code_entropy = config_payload.get("code_entropy", {}) if isinstance(config_payload.get("code_entropy"), dict) else {}
    raw_scoring = code_entropy.get("scoring_v1")
    return build_scoring_v1(raw_scoring, source_path=source_path)


def _build_catalog_model(dimension_order: list[str], dimensions: dict[str, Any], weights: dict[str, Any]) -> dict[str, Any]:
    return {
        "labels": {
            "status": STATUS_LABELS,
            "category": CATEGORY_LABELS,
            "direction": DIRECTION_LABELS,
            "unit": UNIT_LABELS,
            "missing": MISSING_LABELS,
        },
        "dimensions": [
            _dimension_model(name, dimensions[name], weights)
            for name in dimension_order
        ],
    }


def _dimension_model(name: str, dimension: dict[str, Any], weights: dict[str, Any]) -> dict[str, Any]:
    metrics = dimension.get("metrics", {}) if isinstance(dimension.get("metrics"), dict) else {}
    rules = [rule for rule in dimension.get("rules", []) if isinstance(rule, dict)]
    return {
        "key": name,
        "label": dimension.get("label", name),
        "scope": DIMENSION_SCOPES.get(name, "代码本体熵评分维度。"),
        "formula_version": dimension.get("formula_version"),
        "scorecard_weight": dimension.get("scorecard_weight"),
        "entropy_weight": weights.get(WEIGHT_KEYS.get(name, "")),
        "rule_count": len(rules),
        "metric_count": len(metrics),
        "level_bands": dimension.get("level_bands", {}) if isinstance(dimension.get("level_bands"), dict) else {},
        "rules": [_rule_model(rule, metrics) for rule in rules],
    }


def _rule_model(rule: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    metric_id = str(rule.get("metric", ""))
    metric = metrics.get(metric_id) if isinstance(metrics.get(metric_id), dict) else {}
    return {
        "id": rule.get("id"),
        "label": rule.get("label"),
        "category": rule.get("category"),
        "state": rule.get("state"),
        "metric": metric_id,
        "weight": rule.get("weight"),
        "direction": rule.get("direction"),
        "score_if_no_match": rule.get("score_if_no_match"),
        "score_if_missing": rule.get("score_if_missing"),
        "rule_cn": rule.get("rule_cn"),
        "bands": [band for band in rule.get("bands", []) if isinstance(band, dict)],
        "metric_definition": metric,
        "search": _search_blob(rule, metric),
    }


def _render_nav_dimension(dimension: dict[str, Any]) -> str:
    rules = "\n".join(_render_nav_rule(rule) for rule in dimension["rules"])
    title = f"{dimension['label']}，共 {dimension['rule_count']} 条规则。点击可展开或收起。"
    return f"""
    <div class="tree-group" data-dimension="{_esc(dimension['key'])}" data-search="{_esc(_search_blob(dimension))}">
      <button type="button" class="dimension-btn" data-dimension="{_esc(dimension['key'])}" aria-expanded="false" title="{_esc(title)}">
        <span class="dimension-main">
          <span class="chevron" aria-hidden="true">⌄</span>
          <span class="dimension-copy"><span class="dimension-name">{_esc(dimension['label'])}</span><span class="dimension-key"> / {_esc(dimension['key'])}</span></span>
        </span>
        <span class="rule-count" title="{_esc(dimension['label'])}下配置了{_esc(dimension['rule_count'])}条评分规则">{_esc(dimension['rule_count'])} 条规则</span>
      </button>
      <div class="rule-list">{rules}</div>
    </div>"""


def _render_nav_rule(rule: dict[str, Any]) -> str:
    weight = _fmt_number(rule["weight"])
    title = f"{rule['label']}，规则权重 {weight}。权重越高，对当前熵类总分影响越大。"
    return f"""
      <button type="button" class="rule-btn" data-rule-id="{_esc(rule['id'])}" data-search="{_esc(rule['search'])}" title="{_esc(title)}" aria-label="{_esc(title)}">
        <span class="rule-label">{_esc(rule['label'])}</span>
        <span class="rule-weight-mini">权重 {_esc(weight)}</span>
      </button>"""


def _render_overview_card(dimension: dict[str, Any]) -> str:
    entropy_weight = _fmt_percent(dimension["entropy_weight"])
    return f"""
    <article class="overview-card" data-dimension="{_esc(dimension['key'])}">
      <div class="overview-top">
        <div><div class="overview-name">{_esc(dimension['label'])}</div><div class="overview-key">{_esc(dimension['key'])}</div></div>
        <div class="score-pill" title="总熵权重：{_esc(entropy_weight)}。表示该熵类汇总到总熵时的占比。">总熵权重 {_esc(entropy_weight)}</div>
      </div>
      <p class="overview-scope">{_esc(dimension['scope'])}</p>
      <div class="overview-stats">
        <div class="stat"><span>规则数</span><strong>{_esc(dimension['rule_count'])}</strong></div>
        <div class="stat"><span>指标数</span><strong>{_esc(dimension['metric_count'])}</strong></div>
      </div>
    </article>"""


def _search_blob(*items: object) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)


def _fmt_percent(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{float(value) * 100:.1f}%"


def _fmt_number(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value or "-")
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)
