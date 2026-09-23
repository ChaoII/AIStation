import { mkdirSync } from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

import {
  login,
  createTimeSeriesEventTask,
  gotoTimeSeriesWorkbench,
  createTimeSeriesSegment,
  selectTimeSeriesLabel,
} from "./anno-helper";

// 时间序列事件（time_series_event）工作台端到端：上传 CSV 建序列 → 建 time_series_event 任务 →
// echarts 折线图拖选区间生成事件 → 编辑类别 → 保存 → 刷新验证持久化 → 删除二次确认。
// 说明：序列数据经后端 content 端点（text/csv）同源拉取，前端解析为 {time,value} 后经 echarts 渲染，
// 无音频那样跨源解码的 CORS 问题；annotation 读写接口走真实后端以验证持久化。

// 事件类别列表（与后端 time_series_event `classes` 约定一致）
const CLASSES = [
  { id: 1, name: "正常运行", color: "#409eff" },
  { id: 2, name: "异常", color: "#67c23a" },
];

test("time_series_event：拖选生成事件、编辑类别、保存与刷新持久化", async ({ page, request }) => {
  // 截图落到 gitignore 的 test-results/，避免硬编码本机路径
  const shotDir = path.resolve(process.cwd(), "test-results");
  mkdirSync(shotDir, { recursive: true });
  const shot = (name: string) => path.join(shotDir, name);

  const auth = await login(request);
  const { taskId } = await createTimeSeriesEventTask(request, auth, "ts", CLASSES);

  await gotoTimeSeriesWorkbench(page, taskId);

  // 1) 折线图拖选区间生成事件 → 弹「新建事件区间」→ 选类别「正常运行」→ 确定 → 面板出现 1 个事件区间
  await createTimeSeriesSegment(page, 0.2, 0.7);
  const createDialog = page.locator(".el-dialog", { hasText: "新建事件区间" });
  await expect(createDialog).toBeVisible({ timeout: 10_000 });
  await selectTimeSeriesLabel(page, "正常运行");
  await createDialog.getByRole("button", { name: "确定" }).click();
  await expect(createDialog).toBeHidden();
  await expect(page.locator(".time-series-panel .tsp-item")).toHaveCount(1, { timeout: 10_000 });
  await page.screenshot({ path: shot("ts-e2e-1-segment.png") });

  // 2) 编辑类别：面板编辑按钮打开「编辑事件区间」→ 改类别「异常」→ 保存 → 面板类别文案更新
  await page.locator(".time-series-panel .tsp-item .tsp-actions .tsp-btn").first().click();
  const editDialog = page.locator(".el-dialog", { hasText: "编辑事件区间" });
  await expect(editDialog).toBeVisible({ timeout: 10_000 });
  await selectTimeSeriesLabel(page, "异常");
  await editDialog.getByRole("button", { name: "保存" }).click();
  await expect(editDialog).toBeHidden();
  await expect(page.locator(".time-series-panel .tsp-item .tsp-type")).toContainText("异常", {
    timeout: 10_000,
  });

  // 3) 保存 → 无未保存标记（unsaved-dot 归零）
  await page.locator(".ann-footer").getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".unsaved-dot")).toHaveCount(0, { timeout: 10_000 });
  await page.screenshot({ path: shot("ts-e2e-2-saved.png") });

  // 4) 刷新持久化：真实后端读取已保存区间，事件仍在且类别为「异常」
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".time-series-canvas__chart").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".time-series-panel .tsp-item")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator(".time-series-panel .tsp-item .tsp-type")).toContainText("异常", {
    timeout: 15_000,
  });

  // 5) 删除二次确认：点删除 → 出确认框（含「不可恢复」提示）→ 取消保留区间
  await page.locator(".time-series-panel .tsp-item .tsp-actions .tsp-del").first().click();
  const confirm = page.locator(".el-message-box");
  await expect(confirm).toBeVisible({ timeout: 10_000 });
  await expect(confirm).toContainText("不可恢复");
  await confirm.getByRole("button", { name: "取消" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.locator(".time-series-panel .tsp-item")).toHaveCount(1);
});
