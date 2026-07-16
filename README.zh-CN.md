<p align="center"><a href="README.md">English</a></p>

# Stometa Skills

多个业务 Repo，三个作用域，一条 ownership 规则。

`stometa-skills` 是经过真实使用、可移植性检查、隐私检查和行为评测后，对外发布 Agent Skills 的公共仓库。第一版 Prompt 留在孵化层；只有完成 Promotion 的 Skill 才进入这里。

> **当前状态：active incubation baseline v0。** 目前已有 `0` 个 promoted Skill。仓库规则已经生效；第一个 Promotion 完成后必须复盘一次，再决定是否升级为 v1。

## 分层模型

```text
Repository Skill
  -> 在不同 Repo 中重复使用
  -> 私有孵化与评估
  -> 公共 Promotion Review
  -> ownership 转移到 stometa-skills
```

系统把三个问题分开处理：

| 维度 | 取值 | 回答的问题 |
|---|---|---|
| Scope | repository / shared / public | Skill 在什么范围内有效 |
| Visibility | private / public | 谁可以读取源码和证据 |
| Lifecycle | incubating / validated / stable / deprecated | Skill 已经获得多少信任 |

三个维度不能互相推导。跨 Repo 重复不等于适合公开；能够脱敏也不等于值得维护。

## 仓库合同

- `skills/` 保持扁平，只包含完成 Promotion 的 public Skill。Deprecated Skill 作为迁移来源保留，但退出默认 Collection 与安装入口。
- 每个公开 Skill 只在本仓库保留一份 canonical source。
- Repo 路径、命令、凭据和业务事实留在本地 profile。
- Promotion PR 必须包含来源、真实使用证据、trigger 测试、安全检查和安装验证。
- Claude、Codex、Multica 与 installer metadata 都是 adapter，不能复制 Skill 正文形成第二事实源。

完整约定见 [Architecture](docs/architecture.md) 和 [Promotion Policy](docs/promotion-policy.md)。深层文档当前以英文维护；两份 README 会同步产品行为与入口。

## 先选择最小有效作用域

| 当方法具备这些特征 | 放在哪里 | 原因 |
|---|---|---|
| 绑定一个代码库、客户或运行环境 | 对应 Repo | Skill 可以直接使用本地路径和约定，不需要伪装成通用方法 |
| 已在自己的多个 Repo 复用，但仍包含个人信息或敏感证据 | 私有 control plane | 同一个 owner 可以合并与评估，同时不公开原始使用数据 |
| 可移植、可公开检查、经过独立 review，并值得为其他人长期维护 | `stometa-skills` | 公共仓库接管 canonical ownership |

这套架构可以被其他人复用；私有 control plane 只是磊磊当前选择的一种实现。个人、团队或开源维护者都可以只采用自己需要的层级。具体落地方式与可复制 Prompt 见 [Operating Model](docs/operating-model.md)。

## Collections

Collection 是 catalog view，不是物理目录。一个 Skill 可以出现在多个 Collection 中，不需要移动或复制源码。

- Skill Engineering
- Repository and Harness Engineering
- Research and Knowledge Work
- Content and Growth

机器可读定义在 [`catalog/collections.yaml`](catalog/collections.yaml)。

## 安装

首个 Skill 完成 Promotion 前，本仓库不会给出不可验证的安装命令。计划支持的分发入口记录在 [Compatibility](docs/compatibility.md)：

- `skills.sh`：复制后可编辑
- Claude Code / Codex Plugin：托管式安装
- Multica：GitHub 导入与 repository-scoped discovery

Multica 会把这两条路径分开处理。Repository-scoped Skill 留在 checkout 中，由底层 coding tool 发现；Workspace Skill 需要导入、绑定 Agent，并在新 Task 启动时同步。详见 [Multica 使用方式](docs/multica.md)。

## 参与贡献

先读 [CONTRIBUTING.md](CONTRIBUTING.md)。新增 Skill 必须提供 Promotion case；文档、评测和可移植性修复可以直接提交。

## 文档

- [Operating Model](docs/operating-model.md)：采用三层系统，并直接复用审查 Prompt。
- [Architecture](docs/architecture.md)：事实源、作用域与 ownership transfer。
- [Promotion Policy](docs/promotion-policy.md)：提名信号、门槛与决策。
- [Skill Standard](docs/skill-standard.md)：文件结构、评测与安全边界。
- [Multica](docs/multica.md)：repository-scoped、local 与 Workspace Skill 的差异。
- [Compatibility](docs/compatibility.md)：verified、expected 与 unsupported adapter。

## License

Apache-2.0。第三方 adaptation 必须保留原始许可证、来源和修改记录。
