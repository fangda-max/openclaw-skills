#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置工具 - 路径和变量解析
"""

import os
import re
from pathlib import Path


def resolve_variables(value, config, env_vars=None):
    """
    递归解析配置中的变量

    支持的变量格式:
    - ${base_path} - 从 config 中读取
    - ${API_KEY} - 从环境变量读取
    - ${workspace} - 从 config 中读取

    Args:
        value: 要解析的值（可以是 str, dict, list）
        config: 配置字典
        env_vars: 环境变量字典（可选，默认使用 os.environ）

    Returns:
        解析后的值
    """
    if env_vars is None:
        env_vars = os.environ

    if isinstance(value, str):
        # 解析字符串中的变量
        return _resolve_string(value, config, env_vars)

    elif isinstance(value, dict):
        # 递归解析字典
        return {k: resolve_variables(v, config, env_vars) for k, v in value.items()}

    elif isinstance(value, list):
        # 递归解析列表
        return [resolve_variables(item, config, env_vars) for item in value]

    else:
        # 其他类型直接返回
        return value


def _resolve_string(value, config, env_vars):
    """解析字符串中的变量"""
    # 查找所有 ${var} 格式的变量
    pattern = r'\$\{([^}]+)\}'
    matches = re.findall(pattern, value)

    for var_name in matches:
        # 优先从环境变量读取
        if var_name in env_vars:
            replacement = env_vars[var_name]
        # 其次从 config 读取
        elif var_name in config:
            replacement = str(config[var_name])
        else:
            # 变量未定义，保持原样或抛出错误
            raise ValueError(f"未定义的变量: ${{{var_name}}}")

        value = value.replace(f'${{{var_name}}}', replacement)

    return value


def load_config_with_variables(config_path):
    """
    加载配置文件并解析所有变量

    Args:
        config_path: 配置文件路径

    Returns:
        解析后的配置字典
    """
    import json

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 解析所有变量
    resolved_config = resolve_variables(config, config)

    return resolved_config


def validate_paths(config, required_paths):
    """
    验证配置中的路径是否存在

    Args:
        config: 配置字典
        required_paths: 必须存在的路径列表（字典 key）

    Returns:
        (is_valid, errors) - 验证结果和错误列表
    """
    errors = []

    for path_key in required_paths:
        if path_key not in config:
            errors.append(f"缺少配置项: {path_key}")
            continue

        path = config[path_key]

        # 如果是输出路径，检查父目录是否存在
        if 'output' in path_key.lower():
            parent_dir = Path(path).parent
            if not parent_dir.exists():
                errors.append(f"输出目录不存在: {parent_dir}")

        # 如果是输入路径，检查文件/目录是否存在
        elif 'input' in path_key.lower() or 'path' in path_key.lower():
            if not Path(path).exists():
                errors.append(f"路径不存在: {path}")

    return len(errors) == 0, errors


# 示例用法
if __name__ == "__main__":
    # 测试配置
    test_config = {
        "base_path": "D:/Desktop/new-classified",
        "workspace": "/data/workspace",
        "input_file": "${base_path}/input.md",
        "output_file": "${base_path}/output.md",
        "api_key": "${API_KEY}",
        "nested": {
            "path": "${workspace}/data"
        }
    }

    # 设置测试环境变量
    os.environ['API_KEY'] = 'test-key-123'

    # 解析变量
    resolved = resolve_variables(test_config, test_config)

    print("原始配置:")
    print(test_config)
    print("\n解析后配置:")
    print(resolved)
