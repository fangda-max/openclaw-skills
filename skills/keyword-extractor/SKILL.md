---
name: keyword-extractor
description: Intelligently extract core keywords from user requirement descriptions for knowledge base retrieval. Uses LLM to analyze business context and identify 3-5 most relevant terms (2-6 characters each). Supports multiple LLM providers (Claude, OpenAI, MiniMax, Alibaba Cloud, Zhipu). Outputs JSON format with extracted keywords and count.
---

> **依赖安装**:
> - 核心依赖：`pip install requests`
> - Python 3.7+

# Keyword Extractor

## Use This Skill When

- 用户提供了长文本需求描述，需要提取核心关键词
- 作为 Pipeline 的第一步，为后续的知识库检索提供输入
- 需要从业务需求中识别 DICT 系统的模块名或核心功能
- 用户要求"提取关键词""分析需求关键点""识别核心术语"

## Default Deliverables

默认输出文件：
- `keywords.json` - 提取的关键词列表（JSON格式）

输出格式：
```json
{
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "count": 3
}
```

## Hard Rules

- **必须从用户输入中提取实际关键词**：不得使用占位符
- 关键词必须是 DICT 系统的模块名或核心功能
- 每个关键词长度 2-6 个字
- 返回 3-5 个最核心的关键词
- 优先提取文档标题、章节名中的术语
- 输出必须是有效的 JSON 格式

## Workflow

### Step 1: 初始化
1. 加载配置文件 `config.json`
2. 解析环境变量（如 `${API_KEY}`）
3. 初始化 LLM 客户端
4. 加载提示词模板

### Step 2: 提取关键词
1. 接收用户需求描述文本
2. 构建提示词
3. 调用 LLM API
4. 解析 JSON 响应
5. 提取 `keywords` 字段

### Step 3: 验证与输出
1. 验证关键词数量（3-5个）
2. 验证关键词长度（2-6个字）
3. 保存结果到 `keywords.json`
4. 返回关键词列表

## Configuration

### config.json 示例

```json
{
  "base_path": "D:/Desktop/new-classified",
  "llm": {
    "provider": "minimax",
    "api_key": "${API_KEY}",
    "api_url": "https://api.minimaxi.com/v1/chat/completions",
    "model": "MiniMax-M2.7",
    "temperature": 0.1,
    "max_tokens": 500
  },
  "output_file": "${base_path}/keywords.json"
}
```

### 环境变量

```bash
export API_KEY="your-api-key-here"
```

### 支持的 LLM 提供商

- `claude` - Claude (Anthropic)
- `openai` - OpenAI GPT
- `minimax` - MiniMax
- `aliyun` - 阿里云通义千问
- `zhipu` - 智谱 AI

## Usage

### 命令行使用

```bash
cd skills/keyword-extractor
python scripts/extract_keywords.py "标讯管理模块需要实现中标公告的分页查询功能"
```

### Python 代码使用

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'skills' / 'keyword-extractor' / 'scripts'))

from extract_keywords import KeywordExtractor

extractor = KeywordExtractor(config_path='config.json')
keywords = extractor.extract(user_input)
print(f"提取到的关键词: {keywords}")
extractor.save_result(keywords)
```

## Examples

### 示例 1：标讯管理需求

**输入**: 标讯管理模块需要实现中标公告的分页查询功能

**输出**:
```json
{
  "keywords": ["标讯管理", "中标公告", "分页查询"],
  "count": 3
}
```

### 示例 2：商机管理需求

**输入**: 商机管理系统需要支持商机录入、商机跟进、商机转化等功能

**输出**:
```json
{
  "keywords": ["商机管理", "商机录入", "商机跟进", "商机转化"],
  "count": 4
}
```

## Integration with Other Skills

### Pipeline 工作流

```
keyword-extractor (第一步)
    ↓ 输出: keywords.json
precise-knowledge-retriever (第二步)
    ↓ 输入: keywords, 输出: retrieval_result.md
doc-content-optimizer (第三步)
    ↓ 输入: retrieval_result.md, 输出: optimized_result.md
enterprise-requirement-doc-pro (第四步)
    ↓ 输入: optimized_result.md, 输出: PRD文档
```

### 串联使用示例

```python
from extract_keywords import KeywordExtractor
from retrieve import PreciseKnowledgeRetriever
from optimize_document import DocumentOptimizer
from prd_generator import PRDGenerator

# Step 1: 提取关键词
extractor = KeywordExtractor()
keywords = extractor.extract(user_input)

# Step 2: 精确检索
retriever = PreciseKnowledgeRetriever(vector_db_path, kg_path)
result = retriever.retrieve(keywords)

# Step 3: 优化内容
optimizer = DocumentOptimizer(config_path)
optimizer.optimize()

# Step 4: 生成 PRD
generator = PRDGenerator(config_path)
generator.generate(materials_dir)
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
解决方案：设置环境变量或在配置文件中配置

### API 调用失败
解决方案：检查网络连接和 API URL

### JSON 解析失败
解决方案：检查 LLM 返回内容，可能需要调整提示词

### 未提取到关键词
解决方案：检查用户输入是否包含有效的业务术语

## Version

v1.0.0
