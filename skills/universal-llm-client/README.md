# Universal LLM Client

通用 LLM API 客户端，支持多种模型提供商。

## 支持的提供商

- Aliyun (通义千问)
- OpenAI
- Claude (Anthropic)
- GLM (智谱)
- MiniMax

## 使用方法

```python
import sys
from pathlib import Path

# 导入 LLM 客户端
sys.path.append(str(Path(__file__).parent.parent.parent / 'universal-llm-client' / 'scripts'))
from llm_client import UniversalLLMClient

# 配置
config = {
    "provider": "minimax",
    "api_key": "your-api-key",
    "api_url": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
    "model": "MiniMax-M2.7",
    "temperature": 0.3,
    "max_tokens": 2000
}

# 初始化客户端
client = UniversalLLMClient(config)

# 调用
response = client.call("你的提示词")
print(response)
```

## 配置说明

- `provider`: 提供商名称 (aliyun/openai/claude/glm/minimax)
- `api_key`: API 密钥（支持环境变量 API_KEY）
- `api_url`: API 端点
- `model`: 模型 ID
- `temperature`: 温度参数 (0-1)
- `max_tokens`: 最大 token 数

## 特性

- 自动重试机制（默认 3 次）
- 支持环境变量配置 API Key
- 统一的调用接口
