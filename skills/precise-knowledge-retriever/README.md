# Precise Knowledge Retriever

精确匹配知识检索器，从向量库和知识图谱中检索完整文档内容。

## 功能

- 基于关键词精确匹配文档（文件名包含关键词）
- 返回匹配文档的全部内容块
- 结合 ChromaDB 和知识图谱补充上下文
- 数据清洗过滤（当前实现要求至少 10% 的内容块命中关键词）
- 自动格式化为 PRD 原材料

## 依赖

- Python 3.7+
- `chromadb`

## 配置文件

`config.json` 示例：

```json
{
  "base_path": "${WORKSPACE_DATA_DIR}",
  "vector_db_path": "${base_path}/vector-db-materials",
  "kg_path": "${base_path}/knowledge_graph.json",
  "keywords_file": "${base_path}/keywords.json",
  "output_file": "${base_path}/prd_material_precise.md"
}
```

## 使用方法

```bash
cd skills/precise-knowledge-retriever
python scripts/retrieve.py
```

前置条件：必须先运行 `keyword-extractor` 生成 `keywords.json`

## Python 使用

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'skills' / 'precise-knowledge-retriever' / 'scripts'))

from retrieve import PreciseKnowledgeRetriever

retriever = PreciseKnowledgeRetriever(
    vector_db_path='vector-db-materials',
    kg_path='knowledge_graph.json'
)

result = retriever.retrieve(['标讯管理', '中标公告'])
markdown = retriever.format_for_prd(result)
print(markdown[:500])
```

## 使用效果

输入 `keywords.json`：

```json
{
  "keywords": ["标讯管理", "中标公告", "分页查询"],
  "count": 3
}
```

输出 `prd_material_precise.md`：

```markdown
# 知识库检索结果（精确匹配）

关键词: 标讯管理, 中标公告, 分页查询

## 一、匹配的需求文档

### DICT项目管理中心需求分析说明书-标讯管理与中标库结合V1.0.docx
```

## 与其他 Skill 的关系

```text
keyword-extractor (第一步)
    ↓ 输出: keywords.json
precise-knowledge-retriever (第二步) ← 当前 Skill
    ↓ 输出: prd_material_precise.md
doc-content-optimizer (第三步)
    ↓ 输出: prd_material_optimized.md + optimization_report.json
```

作用：作为 Pipeline 的第二步，读取关键词文件，从向量库和知识图谱中精确检索完整文档，为后续内容优化提供原材料。

## 核心特性

1. 精确匹配：只返回文件名包含关键词的文档
2. 完整内容：返回匹配文档的所有内容块，而不是片段
3. 数据清洗：当前代码固定使用 10% 相关性阈值
4. 知识图谱增强：补充依赖模块和关联信息

## 版本

v1.0.0
