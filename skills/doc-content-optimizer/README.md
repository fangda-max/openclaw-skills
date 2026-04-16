# Doc Content Optimizer

优化检索文档的连贯性和可读性，严格保留原始信息。

## 功能

- 使用 LLM 优化文档内容的连贯性和可读性
- 严格保留原始信息（不添加、不删除、不推测）
- 大块分段优化，降低长文档整体截断风险
- 质量验证（完整性 ≥ 95%，一致性 ≥ 70%）
- 自动回滚不合格或疑似截断的优化结果
- 生成详细的质量报告

## 依赖

- Python 3.7+
- `requests`

## 环境变量

必须设置：

```bash
export API_KEY="your-api-key-here"
export WORKSPACE_DATA_DIR="/path/to/data-dir"
```

## 配置文件

`config.json` 示例：

```json
{
  "base_path": "${WORKSPACE_DATA_DIR}",
  "llm": {
    "provider": "minimax",
    "api_key": "${API_KEY}",
    "api_url": "https://api.minimaxi.com/v1/chat/completions",
    "model": "MiniMax-M2.7",
    "temperature": 0.5,
    "max_tokens": 20000
  },
  "input_file": "${base_path}/prd_material_precise.md",
  "output_file": "${base_path}/prd_material_optimized.md",
  "report_file": "${base_path}/optimization_report.json",
  "quality_thresholds": {
    "completeness": 0.95,
    "consistency": 0.70
  }
}
```

## 使用方法

```bash
cd skills/doc-content-optimizer
python scripts/optimize_document.py
```

前置条件：必须先运行 `precise-knowledge-retriever` 生成 `prd_material_precise.md`

## Python 使用

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'skills' / 'doc-content-optimizer' / 'scripts'))

from optimize_document import DocumentOptimizer

optimizer = DocumentOptimizer(config_path='config.json')
optimizer.optimize()
print("优化完成，请读取输出文件和质量报告。")
```

## 当前优化逻辑

1. 读取完整 Markdown 文档
2. 按自然段拆成约 4000 字左右的大块
3. 对每个大块单独调用 LLM
4. 对每个大块做完整性和一致性检查
5. 检测明显截断特征
6. 不合格或疑似截断时回滚原块
7. 合并所有块并输出最终文档

## 质量报告示例

```json
{
  "total_chunks": 4,
  "passed_chunks": 4,
  "failed_chunks": 0,
  "avg_completeness": 1.02,
  "avg_consistency": 0.85,
  "details": [
    {
      "chunk_index": 1,
      "completeness": 1.01,
      "consistency": 0.91,
      "passed": true,
      "original_length": 3920,
      "optimized_length": 3975
    }
  ]
}
```

## 与其他 Skill 的关系

```text
keyword-extractor (第一步)
    ↓ 输出: keywords.json
precise-knowledge-retriever (第二步)
    ↓ 输出: prd_material_precise.md
doc-content-optimizer (第三步) ← 当前 Skill
    ↓ 输出: prd_material_optimized.md + optimization_report.json
enterprise-requirement-doc-pro (第四步)
    ↓ 输入: prd_material_optimized.md
```

## 核心特性

1. 严格保留：不添加原文没有的信息，不删除关键内容
2. 大块分段优化：将长文档拆成较大自然块逐段优化
3. 双重质量验证：完整性 + 一致性
4. 截断检测与自动回滚：发现半截输出时回退原文
5. 详细报告：每个优化块都有质量指标

## 质量指标说明

- 完整性（Completeness） = 优化后字数 / 原始字数
  - ≥ 0.95 为合格
- 一致性（Consistency） = 关键词重叠比例
  - ≥ 0.70 为合格

## 版本

v1.0.0
