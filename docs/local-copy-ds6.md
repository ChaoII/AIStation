# 燃煤业务库本地副本（ds:6）

2026-11-10 从远程只读库 `ds:4`（172.168.100.214:5433/EZDCSZHMC）备份，还原到本地 PG，
并补齐合同、采样制样、细项化验、计划、组态/人脸/小程序等业务数据。

## 1. 备份（源库只读）

```bash
# 在本地 PG 容器内执行（容器可直连远程库）
docker exec -e PGPASSWORD=1234 aistation-pg-rag \
  pg_dump -h 172.168.100.214 -p 5433 -U postgres -d EZDCSZHMC \
  -Fc -f /tmp/ezdcs_20261110.dump
docker cp aistation-pg-rag:/tmp/ezdcs_20261110.dump \
  D:/AIStation/devops/backups/ezdcs_20261110.dump
```

- 文件：`devops/backups/ezdcs_20261110.dump`（71.5 MB，已 gitignore）
- SHA256：`6635B3A4253EB9BD8A9CFEA70121FF49796BB8D68FF054058C6CEF36AAA9E30A`
- 源库体积：517 MB，311 张基础表

## 2. 还原（本地新库，不动 aistation）

```bash
docker exec -e PGPASSWORD=ServBay.dev aistation-pg-rag \
  psql -h 127.0.0.1 -U root -d postgres -c "CREATE DATABASE ezdcs_yuanmei OWNER root"
docker exec -e PGPASSWORD=ServBay.dev aistation-pg-rag \
  pg_restore -h 127.0.0.1 -U root -d ezdcs_yuanmei -j 1 --no-owner --no-privileges \
  /tmp/ezdcs_20261110.dump
```

> ⚠️ 必须用 `-j 1`。`-j 4` 并行还原会出现 `schema "ag_catalog" does not exist` 的会话级错误（源库启用了 AGE，副本没有该扩展），933 条语句被回滚。

还原校验（与源库一致）：批次 287、化验 2527、进煤流水 5711、取煤流水 26498、矿点 65、供应商 103。

## 3. 平台接入

数据源记录 `ai_query_datasources`：

| 字段 | 值 |
|------|-----|
| id / code | 6 / `ezdcs_local`（问数里写 **ds:6**） |
| 名称 | 燃煤业务库（本地副本） |
| 连接 | `127.0.0.1:5432/ezdcs_yuanmei`，root |
| 只读 | true（用户查询只读；补数脚本直连） |

`ds:4` 保持不动 → fuel-v2 评测基准不受影响。

## 4. 补业务数据

```bash
cd backend
uv run python scripts/seed_local_copy_business_data.py
```

脚本幂等（`DEMO-` 前缀主键 + `ON CONFLICT DO NOTHING`），只写 ds:6。补数内容：

| 模块 | 数量 |
|------|------|
| 采购合同 / 质量约束 / 模板条款 | 40 / 50 / 300 |
| 采样单 / 采样明细 | +240 / +240 |
| 制样单 / 制样明细 | +240 / +720 |
| 元素 / 硫 / 热值 / 工业分析 / 水分 | 各 500 |
| 年计划 / 月计划 / 日计划 / 采购月计划 | 1+12 / 12+36 / 30+60 / 12+60 |
| 组态画面分类 / 画面 / 组件 / 引用 | 6 / 12 / 40 / 120 |
| 人脸人员 / 小程序版本 | 20 / 6 |

同时把 ds:4 的**指标、术语、few-shot** 克隆到 ds:6，并补 8 个副本专用指标
（合同数量合计/合同平均单价、采样单数/制样单数、化验平均硫分/发热量、年度/月度计划进煤量）。
概念表 `ai_query_concept.name` 是全局唯一，无法复制同名概念，已跳过。

## 5. 实测（ds:6）

| 问题 | 结果 |
|------|------|
| 燃煤合同一共有多少份 | 40 |
| 燃煤合同的合同数量合计是多少 | 1,829,837 吨 |
| 合同平均单价是多少 | 553.70 元/吨 |
| 化验平均干基全硫是多少 | 0.931% |
| 化验平均发热量是多少 | 4,772.16 Kcal/kg |
| 采样单数 / 制样单数 | 913 / 3084（原 673/2844 + 演示 240） |
| 年度计划进煤量 | 1,200,000 吨 |
| 月度计划进煤量 | 100,000 吨 |
| 当前煤场的存煤量 | 234,938 吨 |
