---
name: opencode-agent
description: 使用 OpenCode AI 编码代理执行编程任务。当用户需要：执行代码任务、代码审查、生成或重构、需要在项目中进行多步骤开发工作时使用。触发场景包括："用 OpenCode 帮我..."、"运行 opencode 任务"、"使用 AI 代理写代码"、"代码审查"等。触发时，应优先考虑使用 sessions_spawn(runtime="acp", agentId="opencode")。
---

# OpenCode Agent Skill

本 Skill 指导如何通过 OpenClaw 调用 OpenCode AI 编码代理来处理复杂的编程任务。

**语言规则**：
- 用户与 OpenClaw 使用 **中文** 对话
- OpenClaw 与 OpenCode 之间必须使用 **英文** 交流
- 当通过 ACP 或 CLI 调用 OpenCode 时，所有指令和上下文都应转换为英文

## 核心能力

1. **ACP 集成 (推荐)**：作为 OpenClaw 的子代理运行，提供结构化的编码能力。
2. **非交互式运行 (`opencode run`)**：适用于直接执行明确的编码指令。
3. **会话管理 (`opencode session`)**：查看历史任务和恢复工作。

## 使用指南

### 1. 作为子代理启动 (ACP) - 推荐方式
对于需要多步迭代、代码生成的任务，直接将其作为 ACP 子代理启动：
- **工具调用**：`sessions_spawn(task="...", runtime="acp", agentId="opencode", thread=true)`
- **优势**：独立会话，支持完整的工作流，不会干扰当前主会话。

### 2. 执行快速编码任务 (CLI)
如果只是简单的单次修改，可以使用 CLI 命令：
- **命令格式**：`opencode run "[指令]"`
- **示例**：`opencode run "在 src/utils.ts 中添加一个高精度的加法函数并编写测试"`

### 3. 进行代码审查
利用 OpenCode 对当前项目进行深度分析。
- **示例**：`opencode run "审查最近的修改并检查是否有潜在的内存泄露或并发问题"`

### 4. 查看状态与用量
- **查看 Token 消耗**：`opencode stats`
- **查看现有会话**：`opencode session list`

## 实战技巧与常见问题

### 📁 原生 Web 应用调试技巧

**问题场景**：开发纯 HTML/JS/CSS 应用时，页面显示空白。

**解决方案步骤**：

1. **优先使用 `file://` 协议直接打开**
   - ❌ 错误：启动 HTTP 服务器 (`python -m http.server`)
   - ✅ 正确：直接在浏览器访问 `file:///C:/path/to/project/index.html`
   - **原因**：原生应用无需后端，HTTP 服务器可能引入 CORS 或路径解析问题。

2. **使用浏览器开发者工具排查**
   - 按 `F12` 打开 DevTools
   - 查看 **Console** 面板的红色错误信息
   - 常见错误：
     - `Failed to load module script`: ES Module 路径错误
     - `Uncaught ReferenceError`: 变量未定义或加载顺序问题
     - `404 Not Found`: 文件路径不正确（检查相对路径）

3. **ES Modules 加载问题的修复模式**
   ```javascript
   // ❌ 错误：在 type="module" 脚本之前运行普通脚本
   <script>window.app = new App()</script>
   <script type="module" src="app.js"></script>
   
   // ✅ 正确：等待 DOMContentLoaded 或在 module 内部初始化
   <script type="module">
       import App from './app.js';
       window.app = new App(document.getElementById('app'));
   </script>
   ```

4. **简化调试策略**
   - 如果模块化代码过于复杂导致空白，先重写为**单文件版本**验证逻辑
   - 确认功能正常后，再逐步拆分为多模块
   - 使用 `console.log()` 在关键位置打点（构造函数、render 函数等）

5. **本地存储调试**
   - 在 DevTools 的 **Application → Local Storage** 查看持久化数据
   - 使用 `localStorage.clear()` 清空测试数据后重试

**案例参考**：Native Calendar 项目从复杂的多模块架构重构为单文件 `index.html` 后，问题立即解决。

---

## 📘 高级工作流：通过 OpenCode 使用 OpenSpec 进行规范驱动开发

OpenSpec 是一个规范驱动开发 (Specification-Driven Development, SDD) 框架，通过与 OpenCode 集成，可以实现从需求对齐到代码实现的完整自动化工作流。

### 什么是 OpenSpec？

OpenSpec 通过以下核心工件确保开发过程的结构化和可追溯性：
- **proposal.md** - 定义"为什么做"和"做什么"
- **design.md** - 技术方案和架构设计
- **specs/** - 详细的需求规范（使用 GIVEN/WHEN/THEN 格式）
- **tasks.md** - 可执行的任务清单

### 完整工作流程

#### 步骤 1：初始化 OpenSpec 项目

```bash
# 为 OpenCode 初始化 OpenSpec 配置
openspec init --tools opencode

# 初始化后会生成：
# - .opencode/skills/openspec-*/SKILL.md (4 个技能文件)
# - .opencode/commands/opsx-*.md (4 个命令文件)
# - openspec/config.yaml (项目配置)
```

#### 步骤 2：创建变更并生成规划工件 (`/opsx:propose`)

**用户指令示例**：
> "使用 OpenSpec 为一个原生 HTML/JS/CSS 日历应用生成完整的规范文档"

**OpenCode 执行流程**：
```bash
# 1. 创建变更目录
openspec new change "native-calendar"

# 2. 自动生成所有规划工件
# - proposal.md (为什么构建 + 核心能力定义)
# - design.md (技术方案：ES Modules + localStorage)
# - specs/calendar-view/spec.md (视图需求规范)
# - specs/event-management/spec.md (事件管理需求)
# - specs/localStorage-persistence/spec.md (数据持久化规范)
# - specs/responsive-design/spec.md (响应式设计要求)
# - tasks.md (41 项可执行任务清单)
```

**关键技巧**：
- 在提案阶段明确**技术栈约束**（如"纯原生，无 npm 依赖"）
- 要求 AI 为每个核心能力编写独立的 `spec.md` 文件
- 检查 `tasks.md` 是否拆解得足够细粒度（每项任务应在 30 分钟 -2 小时内完成）

#### 步骤 3：实现任务 (`/opsx:apply`)

**用户指令示例**：
> "开始实现 native-calendar 变更的所有任务"

**OpenCode 执行流程**：
```bash
# 1. 读取任务清单和规范
openspec status --change "native-calendar" --json

# 2. 逐项实现并更新进度
# - 每完成一个任务，自动标记 tasks.md 中的复选框
# - 遇到模糊需求时暂停并请求用户澄清
# - 保持代码与 spec 的一致性

# 3. 实时查看进度
openspec status --change "native-calendar"
```

**关键技巧**：
- 让 AI 严格按照 `specs/` 中的 `GIVEN/WHEN/THEN` 场景编写测试用例
- 如果实现过程中发现设计缺陷，先修改 `design.md` 再继续编码
- 使用 `openspec instructions <artifact-id>` 获取当前任务的详细上下文

#### 步骤 4：归档变更 (`openspec archive`)

**用户指令示例**：
> "归档 native-calendar 变更，合并规范到主库"

**OpenCode 执行流程**：
```bash
# 归档变更并将 specs 合并到 openspec/specs/ 主库
openspec archive native-calendar --yes

# 结果：
# - 变更移动到 openspec/changes/archive/<date>-native-calendar/
# - 新规范合并到 openspec/specs/ 目录
# - 可在未来项目中复用这些规范
```

### 实战案例：Native Calendar 开发回顾

| 阶段 | 输入 | 输出 | 耗时 |
|------|------|------|------|
| **Propose** | "构建原生日历应用" | 4 个 spec 文件 + 41 项任务 | ~2 分钟 |
| **Apply** | 任务清单 + 规范 | 完整的 HTML/CSS/JS 代码 | ~15 分钟 |
| **Debug** | 空白页面问题 | 单文件重构版本 | ~5 分钟 |
| **Archive** | 完成的变更 | 规范合并到主库 | ~1 分钟 |

**关键收获**：
1. **规范先行**避免了中途需求变更导致的返工
2. **细粒度任务**让 AI 更容易准确执行
3. **可追溯性**：每个代码改动都能对应到具体的 spec 要求

### OpenSpec 常用命令速查

| 命令 | 用途 | 示例 |
|------|------|------|
| `openspec init --tools opencode` | 为 OpenCode 初始化配置 | - |
| `openspec new change "<name>"` | 创建新变更 | `openspec new change "user-auth"` |
| `openspec status --change "<name>"` | 查看变更进度 | 显示 40/41 任务完成 |
| `openspec instructions <artifact>` | 获取工件生成指令 | `openspec instructions proposal` |
| `openspec validate --all` | 验证所有规范结构 | 检查 spec.md 格式 |
| `openspec archive <name> --yes` | 归档变更并合并规范 | - |

### 最佳实践建议

1. **何时使用 OpenSpec？**
   - ✅ 复杂功能开发（需要多模块协作）
   - ✅ 团队协作项目（需要对齐需求）
   - ✅ 长期维护的项目（需要可追溯的规范）
   - ❌ 简单脚本或一次性修改（直接用 `opencode run` 即可）

2. **规范编写技巧**
   - 使用 **GIVEN/WHEN/THEN** 格式编写 Scenarios
   - 每个 `spec.md` 只关注一个核心能力
   - 在 `proposal.md` 中明确标记 **Non-Goals**（不做的事情）

3. **与 OpenCode 配合的节奏**
   - Propose 阶段：让 AI 自主生成，人工审核关键决策
   - Apply 阶段：每完成 5-10 个任务检查一次进度
   - Debug 阶段：遇到问题先查 spec，再调整实现

---

## 🗂️ GitHub 仓库管理：正确的项目组织策略

### ⚠️ 重要教训：技能仓库 vs 应用仓库分离

**曾经犯过的错误**：
- ❌ 将开发的应用代码（如 `riddle-guessing-game/`）推送到 Skill 仓库
- ❌ 混淆了"工具/技能文档"和"实际产品应用"的界限
- ❌ 导致 Skill 仓库变得臃肿，职责不清晰

**正确的做法**：
- ✅ **Skill 仓库** (`openspec-opencode-config`)：只包含技能文档、配置模板、使用指南
- ✅ **Apps 仓库** (`openspec-opencode-apps`)：存放所有通过 OpenSpec 开发的完整应用示例

---

### 📋 双仓库职责划分

| 仓库 | URL | 用途 | 包含内容 | 不包含内容 |
|------|-----|------|----------|------------|
| **Skill 仓库** | [fangda-max/openspec-opencode-config](https://github.com/fangda-max/openspec-opencode-config) | 技能文档与配置 | - `skills/opencode-agent/SKILL.md`<br>- `skills/openspec-workflow/SKILL.md`<br>- 调试技巧、最佳实践<br>- OpenSpec 工作流指南 | ❌ 任何完整的应用代码<br>❌ 示例项目的业务逻辑 |
| **Apps 仓库** | [fangda-max/openspec-opencode-apps](https://github.com/fangda-max/openspec-opencode-apps) | 应用示例集合 | - `native-calendar/`<br>- `skeuomorphic-todo-app/`<br>- `riddle-guessing-game/`<br>- 未来开发的所有应用 | ❌ 技能文档<br>❌ 通用配置模板 |

---

### 🔄 标准工作流程

#### 场景 1：开发新应用

```bash
# 1. 在本地 workspace 使用 OpenSpec + OpenCode 开发
cd C:\Users\18196\.openclaw\workspace
openspec init --tools opencode
opencode run "/opsx:propose 'build a puzzle game'"
opencode run "/opsx:apply puzzle-game"

# 2. 完成后，克隆 Apps 仓库并推送
git clone https://github.com/fangda-max/openspec-opencode-apps.git temp-apps
cp -r puzzle-game/ temp-apps/
cd temp-apps
git add .
git commit -m "feat: Add Puzzle Game app"
git push origin main

# 3. 清理临时目录
cd ..
rm -rf temp-apps
```

#### 场景 2：更新 Skill 文档

```bash
# 1. 编辑本地技能文件
code skills/opencode-agent/SKILL.md

# 2. 克隆 Skill 仓库并推送更新
git clone https://github.com/fangda-max/openspec-opencode-config.git temp-config
cp skills/opencode-agent/SKILL.md temp-config/skills/opencode-agent/
cd temp-config
git add .
git commit -m "docs: Update debugging guide"
git push origin main

# 3. 清理临时目录
cd ..
rm -rf temp-config
```

---

### 🚨 检查清单：推送前必问

在运行 `git push` 之前，请自问：

1. **这是什么类型的内容？**
   - [ ] 技能文档/使用指南 → Skill 仓库
   - [ ] 完整的可运行应用 → Apps 仓库

2. **这个改动会影响什么？**
   - [ ] 教人如何使用工具 → Skill 仓库
   - [ ] 展示工具的实际产出 → Apps 仓库

3. **用户会如何查找这个内容？**
   - [ ] 学习 OpenSpec 流程 → 去 Skill 仓库
   - [ ] 下载示例应用参考 → 去 Apps 仓库

**记忆口诀**：
> 📘 **Skill 仓库存知识**（文档、指南、技巧）  
> 📦 **Apps 仓库存产品**（应用、示例、Demo）

---

### 💡 为什么这样设计？

1. **清晰的职责分离**
   - Skill 仓库保持精简，专注于"如何做事"
   - Apps 仓库自由扩展，展示"做出来的东西"

2. **便于维护**
   - 更新文档时不会意外影响应用代码
   - 添加新应用时不会污染技能文档

3. **用户体验优化**
   - 学习者直奔 Skill 仓库查看教程
   - 开发者前往 Apps 仓库获取源码参考

4. **版本控制独立**
   - Skill 文档可以独立于应用迭代
   - 应用可以按照自己的节奏发布新版本

---

### 📝 历史错误记录

**事件**：2026-03-24  
**问题**：将 `riddle-guessing-game/` 应用推送到 Skill 仓库  
**发现者**：用户及时指出  
**纠正措施**：
1. 从 Skill 仓库移除应用代码 (`git rm -r riddle-guessing-game/`)
2. 重新推送到 Apps 仓库
3. 将此教训写入 Skill 文档防止再犯

**改进结果**：
- ✅ 在文档中新增"GitHub 仓库管理"章节
- ✅ 明确双仓库职责划分表
- ✅ 提供标准工作流程示例
- ✅ 添加推送前检查清单和记忆口诀

---

## 注意事项
- **工作目录**：在运行 `opencode` 前，确保当前 shell 的工作目录处于目标项目的根目录下。
- **权限控制**：OpenCode 在 CLI 模式下可能会请求权限，建议使用 ACP 模式以获得更流畅的集成体验。
- **模型切换**：可以在 `sessions_spawn` 中通过 `model` 参数指定，或在 CLI 中使用 `--model provider/model`。
- **仓库分离**：📘 Skill 文档 → `openspec-opencode-config` | 📦 应用代码 → `openspec-opencode-apps`