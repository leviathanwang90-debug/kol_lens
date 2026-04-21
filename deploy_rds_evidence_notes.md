# PostgreSQL 自建与阿里云 RDS 取舍证据摘录

## 1. PostgreSQL 官方安装文档要点

来源：<https://www.postgresql.org/docs/current/tutorial-install.html>

关键结论：

> PostgreSQL 官方文档明确说明，在站点未预装 PostgreSQL 或用户不确定是否可用时，可以自行安装 PostgreSQL；并且“安装 PostgreSQL 并不困难”，甚至“任何非特权用户都可以安装，不要求 root 权限”。

这说明：**从技术上讲，PostgreSQL 完全支持自建部署，并不以购买托管数据库为前提条件。**

## 2. 阿里云 RDS for PostgreSQL 官方功能页要点

来源：<https://www.alibabacloud.com/help/en/rds/apsaradb-rds-for-postgresql/features-of-apsaradb-rds-for-postgresql>

关键结论：

该页面将 RDS PostgreSQL 定位为一组托管数据库能力集合，涵盖：

- 创建实例
- 主备切换
- 自动扩容
- 只读实例
- 读写分离代理
- 备份与恢复
- 跨地域恢复
- 监控、审计、白名单、SSL 等

这说明：**RDS 的价值主要在于托管化运维、高可用、备份恢复、读写分离与云上管理能力，而不是“项目能否运行”的前置条件。**

## 3. 对 kol_lens 当前阶段的含义

结合当前服务器现场信息：

- 服务器上 PostgreSQL 尚未安装；
- 5432 端口空闲；
- 当前目标是测试环境/手动联调，不是高可用生产集群；
- 用户明确要求避免影响现有产品，而当前不存在已有 PostgreSQL 实例可被误伤。

因此当前更合理的路径是：

> **先在服务器本机安装 PostgreSQL，单独创建 `kol_lens` 数据库和用户，完成联调验证；待后续出现高可用、容灾、自动备份、跨可用区、团队 DBA 运维要求时，再评估迁移到阿里云 RDS。**

## 4. Milvus Standalone 官方资源要求要点

来源：<https://milvus.io/docs/prerequisite-docker.md>

关键结论：

Milvus 官方文档对 Standalone 模式给出的资源要求为：

- **RAM 要求 8GB，推荐 16GB**；
- **CPU 推荐 4 core 或以上**；
- Linux 平台要求 Docker 19.03+ 与 Docker Compose 1.25.1+；
- Standalone 安装时会自动拉起 etcd 与对象存储组件；
- 磁盘性能对 etcd 很关键，官方建议优先使用 SSD / NVMe。

这说明：**Milvus 是当前完整部署链路里最吃资源的组件**。因此在共享服务器上，是否“不会影响其他产品”，关键并不在 PostgreSQL，而在于：

1. 服务器当前可用内存是否足够；
2. CPU 峰值是否已被其他服务占满；
3. Docker 是否已被其他容器大量占用；
4. 磁盘余量和 IOPS 是否还能承受 Milvus + etcd + MinIO 持续写入。
