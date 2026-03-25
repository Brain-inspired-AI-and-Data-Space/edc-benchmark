# EDC Benchmark 指标说明

本文档定义 benchmark 平台统一使用的核心指标口径。

---

## 1. 核心控制面指标

### 1.1 catalog_request_latency_s
- 含义：Consumer 发起 Catalog / Dataset 请求，到收到可解析的 dataset / offer 响应的耗时
- 单位：秒（s）
- 说明：用于衡量目录发现阶段的控制面开销

### 1.2 contract_offer_negotiation_latency_s
- 含义：Consumer 发起 Contract Negotiation 请求，到收到 negotiation_id 的耗时
- 单位：秒（s）
- 说明：只表示“协商启动”开销，不包含等待 agreement 的时间

### 1.3 contract_agreement_latency_s
- 含义：从 negotiation_id 已创建开始，到查询到 contract agreement 的耗时
- 单位：秒（s）
- 说明：用于衡量协商状态推进和 agreement 生成的时间

### 1.4 transfer_initiation_latency_s
- 含义：Consumer 发起 Transfer Process 请求，到收到 transfer_process_id 的耗时
- 单位：秒（s）
- 说明：只表示“传输启动”开销，不包含数据真正传完的时间

---

## 2. 补充指标

### 2.1 transfer_completion_latency_s
- 含义：从 transfer_process_id 已创建开始，到 transfer process 进入完成态的耗时
- 单位：秒（s）
- 说明：不属于四段核心控制面指标，但用于分析传输真正完成所需时间

### 2.2 throughput_mb_s
- 含义：传输吞吐量
- 计算方式：data_size_mb / transfer_completion_latency_s
- 单位：MB/s
- 说明：用于数据面性能对比

### 2.3 control_plane_total_latency_s
- 含义：四段核心控制/编排耗时总和
- 计算方式：
  - negotiation 场景：
    - catalog_request_latency_s
    - + contract_offer_negotiation_latency_s
    - + contract_agreement_latency_s
  - transfer 场景：
    - catalog_request_latency_s
    - + contract_offer_negotiation_latency_s
    - + contract_agreement_latency_s
    - + transfer_initiation_latency_s
- 单位：秒（s）

### transfer_end_to_end_latency_s
- 含义：从发起 Transfer Process 请求到传输完成的总耗时
- 计算方式：
  transfer_initiation_latency_s + transfer_completion_latency_s
- 单位：秒（s）
- 说明：用于对比不同数据规模下的整体传输时间

---

## 3. 状态字段

### 3.1 negotiation_state
- 含义：Negotiation 最终状态
- 常见值：
  - FINALIZED
  - CONFIRMED
  - TERMINATED
  - DECLINED

### 3.2 transfer_state
- 含义：Transfer Process 最终状态
- 常见值：
  - COMPLETED
  - FINISHED
  - DEPROVISIONED
  - FAILED
  - TERMINATED

---

## 4. 成功判定

### 4.1 negotiation_baseline
- success = true 条件：
  - contract_agreement_id 非空
  - negotiation_state 属于 FINALIZED / CONFIRMED

### 4.2 transfer_baseline
- success = true 条件：
  - contract_agreement_id 非空
  - transfer_state 属于 COMPLETED / FINISHED / DEPROVISIONED

---

## 5. 输出文件中的对应关系

### metrics.csv
每一行表示一次 run 的原始结果。

### summary.json
聚合字段统一包含：
- *_avg
- *_min
- *_max

聚合对象范围仅包括：
- catalog_request_latency_s
- contract_offer_negotiation_latency_s
- contract_agreement_latency_s
- transfer_initiation_latency_s
- transfer_completion_latency_s
- control_plane_total_latency_s
- throughput_mb_s
