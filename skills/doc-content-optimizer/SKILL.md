---
name: doc-content-optimizer
description: Optimize document coherence and readability using LLM while strictly preserving original information. Uses large-block segmented optimization to reduce truncation risk, validates quality with completeness ≥95% and consistency ≥70%, and automatically rolls back failed or truncated outputs.
---

> **依赖安装**:
> - 核心依赖：`pip install requests`
> - Python 3.7+

# Doc Content Optimizer

## Use This Skill When

- 需要优化检索文档的连贯性和可读性
- 作为 Pipeline 的第三步，优化检索到的原材料文档
- 需要在保留原始信息的前提下改善文档质量
- 用户要求“优化文档”“改善可读性”“整理内容”

## Default Deliverables

默认输出文件：
- `prd_material_optimized.md` - 优化后的文档（Markdown 格式）
- `optimization_report.json` - 质量报告（JSON 格式）

## Hard Rules

- 严格保留原始信息：不添加、不删除、不推测
- 质量验证：完整性 ≥ 95%，一致性 ≥ 70%
- 自动回滚：不合格或疑似截断的优化结果自动回滚到原文
- 只优化连贯性和可读性，不改变语义
- 输出必须是有效的 Markdown 格式

## Workflow

### Step 1: 初始化

1. 加载配置文件 `config.json`
2. 解析环境变量（如 `${API_KEY}` 和 `${WORKSPACE_DATA_DIR}`）
3. 初始化 LLM 客户端
4. 读取输入文档 `prd_material_precise.md`

### Step 2: 大块分段优化

1. 将长文档按自然段拆成约 4000 字左右的大块
2. 对每个大块调用 LLM 优化
3. 计算优化后的质量指标
4. 检测输出是否存在明显截断特征
5. 不达标或疑似截断则回滚到原文

### Step 3: 生成报告与输出

1. 合并所有优化块
2. 统计优化结果（成功/失败数量）
3. 生成详细质量报告
4. 保存优化后文档到 `prd_material_optimized.md`
5. 保存质量报告到 `optimization_report.json`

## Configuration

### config.json 示例

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

## Usage

### 命令行使用

```bash
cd skills/doc-content-optimizer
python scripts/optimize_document.py
```

前置条件：必须先运行 `precise-knowledge-retriever` 生成 `prd_material_precise.md`

### Python 代码使用

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'skills' / 'doc-content-optimizer' / 'scripts'))

from optimize_document import DocumentOptimizer

optimizer = DocumentOptimizer(config_path='config.json')
optimizer.optimize()
print("优化完成，请读取输出文件和质量报告。")
```

## Examples

### 示例：长文档分段优化

输入：
- 一份 1 万到 2 万字的检索结果 Markdown 文档

输出：
- 一份按大块分段优化后的完整 Markdown 文档
- 一份包含每个优化块质量指标的 JSON 报告

质量报告示例：

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

## Integration with Other Skills

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

## Dependencies

### Internal Dependencies

- `universal-llm-client` - 通用 LLM 客户端
  - `llm_client.py` - LLM API 调用
  - `config_utils.py` - 配置文件解析

### External Dependencies

- `requests` - HTTP 请求库
- Python 标准库：`json`, `os`, `sys`, `re`, `pathlib`

## Error Handling

### API Key 未设置

解决方案：设置环境变量 `API_KEY`

### 输入文件不存在

解决方案：先运行 `precise-knowledge-retriever` 生成 `prd_material_precise.md`

### 输出疑似截断

解决方案：当前代码会自动回滚该优化块原文，并在质量报告中记录

## Core Features

### 1. 严格保留原始信息

- 不添加原文没有的信息
- 不删除关键内容
- 只优化表达方式

### 2. 大块分段优化

- 将长文档拆成较大的自然块
- 降低整篇一次优化带来的输出截断风险

### 3. 自动回滚机制

- 实时验证每个优化块的质量
- 疑似截断或不达标立即回滚到原文

### 4. 详细质量报告

- 每个优化块的质量指标
- 成功/失败统计
- 平均质量指标

## Version

v1.0.0
