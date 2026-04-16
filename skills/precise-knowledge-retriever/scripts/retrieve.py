#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
精确匹配知识检索器
1. 精确匹配文档（文件名包含关键词）
2. 返回完整文档的所有分块
3. 数据清洗过滤
4. 结合知识图谱补充依赖信息
"""

import os
import sys
import json
from pathlib import Path

# 导入配置工具
sys.path.append(str(Path(__file__).parent.parent.parent / 'universal-llm-client' / 'scripts'))
from config_utils import load_config_with_variables

import sys
import json
from pathlib import Path

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import io
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except:
        pass

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ 请先安装 chromadb: pip install chromadb")
    sys.exit(1)


class PreciseKnowledgeRetriever:
    """
    精确匹配知识检索器
    """

    def __init__(self, vector_db_path, kg_path):
        """初始化"""
        # 连接向量库
        self.client = chromadb.PersistentClient(
            path=vector_db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_collection('dict_materials_with_metadata')

        # 加载知识图谱
        with open(kg_path, 'r', encoding='utf-8') as f:
            self.kg = json.load(f)

        self.nodes = {node['id']: node for node in self.kg['nodes']}
        self.edges = self.kg['edges']

        print(f"✅ 精确匹配检索器初始化成功")
        print(f"   向量库: {self.collection.count()} 条向量")
        print(f"   知识图谱: {len(self.nodes)} 个节点")

    def retrieve(self, keywords, province=None, exact_match=True):
        """
        精确匹配检索

        Args:
            keywords: 关键词列表或单个关键词
            province: 省份筛选
            exact_match: 是否精确匹配文件名

        Returns:
            dict: 检索结果
        """
        if isinstance(keywords, str):
            keywords = [keywords]

        print(f"\n🔍 精确匹配检索")
        print(f"   关键词: {', '.join(keywords)}")
        if province:
            print(f"   省份: {province}")
        print("-" * 80)

        # Step 1: 从向量库获取所有数据
        print(f"\n📊 Step 1: 获取向量库数据...")
        all_data = self.collection.get(include=['documents', 'metadatas'])

        # Step 2: 精确匹配文档
        print(f"\n🎯 Step 2: 精确匹配文档...")
        matched_docs = self._exact_match_documents(
            all_data, keywords, province
        )

        if not matched_docs:
            print(f"   ❌ 未找到匹配的文档")
            return None

        print(f"   ✅ 找到 {len(matched_docs)} 个匹配文档")

        # Step 3: 获取完整文档内容
        print(f"\n📄 Step 3: 获取完整文档内容...")
        full_documents = self._get_full_documents(matched_docs, all_data)

        # Step 4: 数据清洗
        print(f"\n🧹 Step 4: 数据清洗...")
        cleaned_documents = self._clean_documents(full_documents, keywords)

        # Step 5: 知识图谱补充
        print(f"\n🔗 Step 5: 知识图谱补充...")
        kg_info = self._get_kg_info(cleaned_documents)

        result = {
            "keywords": keywords,
            "province": province,
            "matched_documents": cleaned_documents,
            "kg_info": kg_info,
            "summary": {
                "total_documents": len(cleaned_documents),
                "total_chunks": sum(len(doc['chunks']) for doc in cleaned_documents),
                "modules": list(set(doc['module'] for doc in cleaned_documents))
            }
        }

        print(f"\n✅ 检索完成")
        print(f"   文档数: {result['summary']['total_documents']}")
        print(f"   内容块数: {result['summary']['total_chunks']}")
        print(f"   涉及模块: {len(result['summary']['modules'])}")

        return result

    def _exact_match_documents(self, all_data, keywords, province):
        """精确匹配文档"""
        matched = {}

        for doc, meta in zip(all_data['documents'], all_data['metadatas']):
            file_name = meta.get('file_name', '')

            # 省份过滤
            if province and meta.get('scope') != province:
                continue

            # 关键词匹配（文件名包含任一关键词）
            if any(keyword in file_name for keyword in keywords):
                if file_name not in matched:
                    matched[file_name] = {
                        'file_name': file_name,
                        'scope': meta.get('scope', 'N/A'),
                        'module': meta.get('module_name', 'N/A'),
                        'doc_type': meta.get('doc_type', 'N/A'),
                        'chunks': []
                    }

        for file_name in matched:
            print(f"   ✓ {file_name}")

        return matched

    def _get_full_documents(self, matched_docs, all_data):
        """获取完整文档的所有分块"""
        for doc, meta in zip(all_data['documents'], all_data['metadatas']):
            file_name = meta.get('file_name', '')

            if file_name in matched_docs:
                matched_docs[file_name]['chunks'].append({
                    'chunk_index': meta.get('chunk_index', 0),
                    'total_chunks': meta.get('total_chunks', 1),
                    'content': doc
                })

        # 按 chunk_index 排序
        for doc_name in matched_docs:
            matched_docs[doc_name]['chunks'].sort(key=lambda x: x['chunk_index'])

        return list(matched_docs.values())

    def _clean_documents(self, documents, keywords):
        """数据清洗：过滤掉不相关的内容"""
        cleaned = []

        for doc in documents:
            # 检查文档是否真的相关
            file_name = doc['file_name']

            # 规则1：文件名必须包含关键词
            if not any(keyword in file_name for keyword in keywords):
                print(f"   ✗ 过滤: {file_name} (文件名不匹配)")
                continue

            # 规则2：内容相关性检查（至少30%的块包含关键词）
            relevant_chunks = 0
            for chunk in doc['chunks']:
                if any(keyword in chunk['content'] for keyword in keywords):
                    relevant_chunks += 1

            relevance_ratio = relevant_chunks / len(doc['chunks']) if doc['chunks'] else 0

            if relevance_ratio < 0.1:  # 至少10%的块相关
                print(f"   ✗ 过滤: {file_name} (内容相关性 {relevance_ratio:.1%} < 10%)")
                continue

            print(f"   ✓ 保留: {file_name} (相关性 {relevance_ratio:.1%})")
            cleaned.append(doc)

        return cleaned

    def _get_kg_info(self, documents):
        """从知识图谱获取补充信息"""
        kg_info = {
            "modules": {},
            "dependencies": {},
            "related_documents": {}
        }

        # 提取涉及的模块
        modules = set()
        for doc in documents:
            module = doc['module']
            if module and module != 'N/A':
                # 提取模块名（去掉编号）
                if '_' in module:
                    module_name = module.split('_', 1)[1] if len(module.split('_')) > 1 else module
                else:
                    module_name = module
                modules.add(module_name)

        # 查询知识图谱
        for module_name in modules:
            module_node = None
            for node in self.nodes.values():
                if node['type'] == 'Module' and module_name in node['name']:
                    module_node = node
                    break

            if not module_node:
                continue

            kg_info["modules"][module_name] = module_node['name']

            # 查询依赖
            depends_on = []
            depended_by = []

            for edge in self.edges:
                if edge['from'] == module_node['id'] and edge['type'] == 'DEPENDS_ON':
                    target = self.nodes.get(edge['to'])
                    if target:
                        depends_on.append(target['name'])

                if edge['to'] == module_node['id'] and edge['type'] == 'DEPENDS_ON':
                    source = self.nodes.get(edge['from'])
                    if source:
                        depended_by.append(source['name'])

            kg_info["dependencies"][module_name] = {
                "depends_on": depends_on,
                "depended_by": depended_by
            }

            # 查询相关文档
            docs = []
            for edge in self.edges:
                if edge['from'] == module_node['id'] and edge['type'] == 'HAS_DOCUMENT':
                    doc_node = self.nodes.get(edge['to'])
                    if doc_node:
                        docs.append(doc_node['name'])

            kg_info["related_documents"][module_name] = docs

        return kg_info

    def format_for_prd(self, result):
        """格式化为 PRD 原材料"""
        if not result:
            return "# 未找到匹配的文档\n"

        output = []

        output.append("# 知识库检索结果（精确匹配）")
        output.append(f"\n关键词: {', '.join(result['keywords'])}\n")

        # 1. 匹配的文档
        output.append("## 一、匹配的需求文档\n")

        for doc in result['matched_documents']:
            output.append(f"### {doc['file_name']}\n")
            output.append(f"**省份**: {doc['scope']}")
            output.append(f"**模块**: {doc['module']}")
            output.append(f"**文档类型**: {doc['doc_type']}")
            output.append(f"**内容块数**: {len(doc['chunks'])}\n")

            output.append("**完整内容**:\n")

            # 合并所有块
            full_content = "\n\n".join(
                chunk['content'] for chunk in doc['chunks']
            )

            output.append(f"```\n{full_content}\n```\n")
            output.append("-" * 80 + "\n")

        # 2. 知识图谱信息
        output.append("## 二、模块依赖关系\n")

        kg_info = result['kg_info']

        for module_name, deps in kg_info['dependencies'].items():
            output.append(f"### {module_name}\n")

            if deps['depends_on']:
                output.append(f"**依赖于**: {', '.join(deps['depends_on'])}\n")

            if deps['depended_by']:
                output.append(f"**被依赖于**: {', '.join(deps['depended_by'])}\n")

            # 相关文档
            related = kg_info['related_documents'].get(module_name, [])
            if related:
                output.append(f"\n**该模块的其他相关文档** ({len(related)} 个):\n")
                for doc in related[:5]:
                    output.append(f"- {doc}\n")
                if len(related) > 5:
                    output.append(f"- ... 还有 {len(related) - 5} 个文档\n")

            output.append("\n")

        # 3. 摘要
        output.append("## 三、检索摘要\n")
        summary = result['summary']
        output.append(f"- 匹配文档数: {summary['total_documents']}")
        output.append(f"- 总内容块数: {summary['total_chunks']}")
        output.append(f"- 涉及模块: {', '.join(summary['modules'])}\n")

        return "\n".join(output)


def main():
    """从配置文件读取参数并执行检索"""
    import sys

    # 获取配置文件路径
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        # 默认使用 skill 目录下的 config.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skill_dir = os.path.dirname(script_dir)
        config_path = os.path.join(skill_dir, "config.json")

    # 加载配置
    config = load_config_with_variables(config_path)

    print("="*80)
    print("精确匹配知识检索器")
    print("="*80)
    print(f"[OK] 配置文件: {config_path}")

    # 初始化检索器
    retriever = PreciseKnowledgeRetriever(
        vector_db_path=config['vector_db_path'],
        kg_path=config['kg_path']
    )
    print(f"[OK] 向量数据库: {config['vector_db_path']}")
    print(f"[OK] 知识图谱: {config['kg_path']}")

    # 读取关键词
    keywords_file = config['keywords_file']
    if not os.path.exists(keywords_file):
        print(f"\n❌ 错误: 关键词文件不存在: {keywords_file}")
        print("请先运行 keyword-extractor skill 生成关键词文件")
        sys.exit(1)

    with open(keywords_file, 'r', encoding='utf-8') as f:
        keywords_data = json.load(f)
        keywords = keywords_data.get('keywords', [])

    if not keywords:
        print(f"\n❌ 错误: 关键词文件为空: {keywords_file}")
        sys.exit(1)

    print(f"\n[KEYWORDS] 从 {keywords_file} 读取到 {len(keywords)} 个关键词:")
    print(f"   {', '.join(keywords)}")

    # 执行检索
    print(f"\n{'='*80}")
    print("开始检索")
    print("="*80)

    result = retriever.retrieve(
        keywords=keywords,
        province=config.get('province'),
        exact_match=config.get('exact_match', True)
    )

    if result:
        # 格式化为 PRD 原材料
        print(f"\n{'='*80}")
        print("格式化为 PRD 原材料")
        print("="*80)

        prd_material = retriever.format_for_prd(result)

        # 保存到文件
        output_file = config['output_file']
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(prd_material)

        print(f"\n✅ 原材料已保存到: {output_file}")
    else:
        print("\n⚠️  未检索到任何结果")


if __name__ == "__main__":
    main()
