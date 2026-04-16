# Keyword Extractor

从用户需求描述中智能提取核心关键词，用于知识库检索。

## 功能

- 使用 LLM 智能分析需求文本
- 提取业务相关的核心关键词
- 支持多种 LLM 提供商（Claude, OpenAI, MiniMax, 阿里云, 智谱）
- 自动保存提取结果为 JSON 格式

## 依赖

- Python 3.7+
- requests

## 环境变量

必须设置:
```bash
export API_KEY="your-api-key-here"
```

## 配置文件

config.json 示例:
```json
{
  "base_path": "D:/Desktop/new-classified",
  "llm": {
    "provider": "claude",
    "api_key": "${API_KEY}",
    "api_url": "https://api.xxdlzs.top/v1/messages",
    "model": "claude-opus-4-6",
    "temperature": 0.1,
    "max_tokens": 500
  },
  "output_file": "${base_path}/keywords.json"
}
```

## 使用方法

```bash
cd skills/keyword-extractor
python scripts/extract_keywords.py "标讯管理模块需要实现中标公告的分页查询功能"
```

## 使用效果

**输入**:
```
标讯管理模块需要实现中标公告的分页查询功能，支持按项目名称、中标单位等条件筛选
```

**输出** (keywords.json):
```json
{
  "keywords": ["标讯管理", "中标公告", "分页查询"],
  "count": 3
}
```

## 与其他 Skill 的关系

```
keyword-extractor (第一步)
    ↓ 输出: keywords.json
precise-knowledge-retriever (第二步)
    ↓ 输出: prd_material_precise.md
doc-content-optimizer (第三步)
    ↓ 输出: prd_material_optimized.md + optimization_report.json
```

**作用**: 作为 Pipeline 的第一步，从用户长文本需求中提取关键词，为后续的精确检索提供输入。

## 错误处理

- API Key 未设置：显示详细的设置指南
- API 调用失败：自动重试 3 次
- JSON 解析失败：返回空列表

## 版本

v1.0.0
