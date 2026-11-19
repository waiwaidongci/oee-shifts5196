# 002 工单跨班对账

新增厂商工单对账表，原报告（oeeruns）与其冻结快照不改动：

- `reconcile_batches`：批次（`batch_key` 唯一做幂等，`digest` 为批次内容SHA256，`run_id` 指向已复核报告，需求/确认/待核合计，操作者与时间）。
- `reconcile_orders`：批内工单（工单号、设备、日期、起止分钟、需求、已确认、待核）。
- `reconcile_allocations`：确认归属明细（批次、工单、报告、班次键=报告快照内序号，冗余设备/日期/起止便于独立查账，数量）。

班次剩余良品=快照`good`-该报告全部`reconcile_allocations.qty`合计；确认整批在事务内对报告行加锁重算，同`batch_key`重试直接返回原批次不重复占用；无解批次不写以上三表，仅留审计。SQLAlchemy启动自动建表；已有库升级执行同等DDL即可。
