# 后端逻辑文档提取摘要

## 文档标题
创意逻辑 / 用户洞察 / 落地建议（极深全图景拆解）

## 五层架构

### 一、触点层（前端交互与意图转译机制）
- **意图解析器（LLM Intent Parser）**：使用 Few-shot CoT System Prompt，强制 LLM 输出强类型 JSON
- 输出结构包含：hard_filters（硬筛选）、soft_vectors（软向量提示）、elastic_weights（容忍度权重1-5）
- **隐性反馈的 UI 映射**：选中(+1.0)、待定(+0.2)、淘汰(-1.0)

### 二、调度层（贪心降级与并发中台）
- **弹性降级算法（Constraint Relaxation Tree）**：基于 elastic_weights 构建最小优先队列，每次降级弹出权重最低条件
- 数值型条件执行平滑扩展：C_new = [C_min × 0.7, C_max × 1.3]
- **异步任务队列（Celery Worker Flow）**：
  - 前台请求 → 后端返回 Task_ID → 前台轮询
  - Worker 1: Milvus 向量库混合检索（0.5s）
  - Worker 2: 组装 Payload 访问小红书接口（2-5s）
  - 数据写入 Redis 缓存并推送前端，后台 GPU 集群进行特征提取

### 三、解剖层（多模态特征提纯流水线 DAG）
- **Node 1 (Data Ingest)**：下载图片，Resize 到 224×224，存入 OSS
- **Node 2 (Semantic Split)**：YOLO 分割（Mask_Person + Mask_Background），PaddleOCR 提取文字
- **Node 3 (Parallel Embedding)**：
  - Thread A: InsightFace → 512维 V_face
  - Thread B: CLIP Vision → 768维 V_scene
  - Thread C: CLIP Text → 768维 V_text
- **Node 4 (Temporal Fusion)**：时序衰减注意力，30天滑动窗口，指数级衰减

### 四、大脑层（向量运算法则与推荐）
- **Hybrid Ranking Formula**：余弦相似度 + Min-Max归一化 + 商业性价比函数 + 业务超参数
- **Rocchio 向量平移（核心黑科技）**：
  - 选中组(S)平均向量 × 正向权重β(0.75)
  - 淘汰组(R)平均向量 × 负向权重γ(0.25)
  - V_next_query = V_original 朝S拉近，从R推远

### 五、基建层（数据 Schema 设计）
- **PostgreSQL**：influencer_basics（基础信息）、campaign_history（品牌偏好沉淀）
- **Milvus**：influencer_multimodal_vectors（标量索引 + 多维向量：v_face 512维、v_scene 768维、v_overall_style 768维）
- **Redis**：缓存层

## 技术栈总结
- LLM + Few-shot CoT（意图解析）
- Celery（异步任务队列）
- YOLO + PaddleOCR（图像分割与OCR）
- InsightFace + CLIP（多模态嵌入）
- Milvus（向量数据库，混合检索）
- PostgreSQL（关系型数据库）
- Redis（缓存）
- GPU 集群（特征提取）
