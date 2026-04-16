---
name: precise-knowledge-retriever
description: Precisely retrieve complete document content from vector database and knowledge graph based on keywords. Performs exact filename matching, returns all content chunks, cleans low-relevance results, and formats the output as PRD source material.
---

> **依赖安装**:
> - 核心依赖：`pip install chromadb`
> - Python 3.7+

# Precise Knowledge Retriever

## Use This Skill When

- 需要基于关键词精确检索完整文档内容
- 作为 Pipeline 的第二步，接收关键词并检索知识库
- 需要从向量库和知识图谱中获取完整文档内容块
- 用户要求“检索文档”“查找相关资料”“获取完整内容”

## Default Deliverables

默认输出文件：
- `prd_material_precise.md` - 检索到的完整文档内容（Markdown 格式）

## Hard Rules

- 必须精确匹配文档名：只返回文件名包含关键词的文档
- 返回完整内容：返回匹配文档的所有内容块，不是片段
- 数据清洗：当前代码固定要求至少 10% 的内容块命中关键词
- 知识图谱补充：使用知识图谱补充依赖模块和关联信息
- 输出必须是有效的 Markdown 格式

## Workflow

### Step 1: 初始化

1. 加载配置文件 `config.json`
2. 连接 ChromaDB 向量库
3. 加载知识图谱 JSON 文件
4. 读取关键词文件 `keywords.json`

### Step 2: 精确匹配检索

1. 从 `keywords.json` 读取关键词列表
2. 在向量库中查询文档元数据
3. 精确匹配：文件名包含任一关键词
4. 获取匹配文档的所有内容块

### Step 3: 数据清洗与输出

1. 统计每个文档命中关键词的内容块比例
2. 过滤低相关性内容（当前实现阈值为 10%）
3. 使用知识图谱补充关联信息
4. 格式化为 Markdown 文档
5. 保存到 `prd_material_precise.md`

## Configuration

### config.json 示例

```json
{
  "base_path": "${WORKSPACE_DATA_DIR}",
  "vector_db_path": "${base_path}/vector-db-materials",
  "kg_path": "${base_path}/knowledge_graph.json",
  "keywords_file": "${base_path}/keywords.json",
  "output_file": "${base_path}/prd_material_precise.md"
}
```

### 配置参数说明

- `vector_db_path` - ChromaDB 向量库路径
- `kg_path` - 知识图谱 JSON 文件路径
- `keywords_file` - 关键词输入文件（由 `keyword-extractor` 生成）
- `output_file` - 检索结果输出文件
- `province` - 可选省份筛选（通过自定义配置调用时使用）
- `exact_match` - 预留参数，当前实现仍按文件名精确匹配为主

## Usage

### 命令行使用

```bash
cd skills/precise-knowledge-retriever
python scripts/retrieve.py
```

前置条件：必须先运行 `keyword-extractor` 生成 `keywords.json`

### Python 代码使用

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

## Integration with Other Skills

```text
keyword-extractor (第一步)
    ↓ 输出: keywords.json
precise-knowledge-retriever (第二步) ← 当前 Skill
    ↓ 输出: prd_material_precise.md
doc-content-optimizer (第三步)
    ↓ 输出: prd_material_optimized.md
enterprise-requirement-doc-pro (第四步)
    ↓ 输出: PRD 文档
```

## Dependencies

### Internal Dependencies

- `universal-llm-client/config_utils.py` - 配置文件变量解析

### External Dependencies

- `chromadb` - 向量数据库
- Python 标准库：`json`, `os`, `sys`, `pathlib`

### Data Dependencies

- 向量库：ChromaDB 格式的向量数据库
- 知识图谱：JSON 格式的知识图谱文件

## Error Handling

### 向量库不存在

解决方案：检查 `vector_db_path` 配置，确保向量库已构建

### 知识图谱文件不存在

解决方案：检查 `kg_path` 配置，确保知识图谱文件存在

### 关键词文件不存在

解决方案：先运行 `keyword-extractor` 生成 `keywords.json`

### 未找到匹配文档

解决方案：
1. 检查关键词是否正确
2. 尝试更通用的关键词
3. 检查向量库是否包含相关文档

## Core Features

### 1. 精确匹配

- 文件名包含关键词即匹配
- 避免语义漂移

### 2. 完整内容

- 返回匹配文档的所有内容块
- 保证信息完整性

### 3. 数据清洗

- 统计内容块命中率
- 自动过滤低相关性内容
- 当前代码固定阈值为 10%

### 4. 知识图谱增强

- 补充依赖模块信息
- 添加关联功能说明

## Version

v1.0.0
