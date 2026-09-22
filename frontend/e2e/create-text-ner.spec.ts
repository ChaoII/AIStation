import { readFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { test, expect, type Route } from "@playwright/test";

import {
  gotoTextNerWorkbench,
  selectTextEntity,
  readEntityTexts,
  pickSelectOption,
} from "./anno-helper";

// 文本 NER 工作台端到端（前端隔离验证）：拦截 annotation 接口，物料化一个 text_ner 任务，
// 验证只读拖选生成实体、span-click 实体编辑（含删除）、同句关系创建、保存与刷新的持久化。
// 说明：后端 `task/create` 的 `classes` 目前为 list[dict]，尚无法注入 text_ner 的
// `{entities, relations}` 字典，故本用例走前端路由隔离（mock），可独立于任务创建表单运行。

const TEXT = readFileSync(fileURLToPath(new URL("./fixtures/sample.txt", import.meta.url)), "utf-8");

const CLASSES = {
  entities: [
    { id: 1, name: "城市", color: "#409eff" },
    { id: 2, name: "人物", color: "#67c23a" },
  ],
  relations: [{ id: 1, name: "位于" }],
};

let savedAnnotations: any[] = [];

function json(route: Route, body: any) {
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
}

test("文本 NER 工作台：拖选实体、编辑、同句建关系、保存与持久化", async ({ page }) => {
  savedAnnotations = [];
  // 截图落到 gitignore 的 test-results/，避免硬编码本机路径
  const shotDir = path.resolve(process.cwd(), "test-results");
  mkdirSync(shotDir, { recursive: true });
  const shot = (name: string) => path.join(shotDir, name);

  // 拦截 annotation 接口，物料化文档与标注读写。
  await page.route("**/api/v1/annotation/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes("/task/") && path.endsWith("/detail")) {
      return json(route, {
        code: 0,
        msg: "ok",
        data: {
          id: 1,
          dataset_id: 1,
          name: "文本NER任务",
          task_type: "text_ner",
          classes: CLASSES,
          status: "pending",
        },
      });
    }
    if (path.endsWith("/document/list")) {
      return json(route, {
        code: 0,
        msg: "ok",
        data: {
          items: [
            {
              id: 100,
              dataset_id: 1,
              filename: "sample.txt",
              character_count: TEXT.length,
              line_count: TEXT.split("\n").length,
              status: "in_progress",
              locked_by: null,
              locked_at: null,
              annotation_count: savedAnnotations.length,
            },
          ],
        },
      });
    }
    if (path.includes("/document/detail/")) {
      return json(route, {
        code: 0,
        msg: "ok",
        data: {
          id: 100,
          dataset_id: 1,
          filename: "sample.txt",
          object_key: "x",
          content_hash: "x",
          encoding: "utf-8",
          character_count: TEXT.length,
          line_count: TEXT.split("\n").length,
          status: "in_progress",
          locked_by: null,
          locked_at: null,
          annotation_count: savedAnnotations.length,
        },
      });
    }
    if (path.includes("/document/content/")) {
      return route.fulfill({ contentType: "text/plain; charset=utf-8", body: TEXT });
    }
    if (/\/document\/lock\/\d+$/.test(path)) {
      return json(route, { code: 0, msg: "ok", data: { locked: false, locked_by: null } });
    }
    if (path.includes("/document/unlock/")) {
      return json(route, { code: 0, msg: "ok", data: null });
    }
    if (path.endsWith("/anno/document/load")) {
      return json(route, {
        code: 0,
        msg: "ok",
        data: { annotation_data: savedAnnotations, version: savedAnnotations.length ? 2 : 1 },
      });
    }
    if (path.endsWith("/anno/document/save")) {
      savedAnnotations = route.request().postDataJSON()?.annotations || [];
      return json(route, {
        code: 0,
        msg: "保存成功",
        data: { version: 2, annotation_count: savedAnnotations.length },
      });
    }
    return route.continue();
  });

  await gotoTextNerWorkbench(page, 1);

  // 1) 加载：文档全文渲染，顶部显示文件名与字符数（docMeta 上屏）
  await expect(page.locator(".text-ner-canvas .cm-content .cm-line").first()).toBeVisible();
  await expect(page.locator(".ann-header .doc-meta")).toContainText("sample.txt");
  await page.screenshot({ path: shot("ner-final-1-loaded.png") });

  // 2) 拖选生成两个实体（同句、无重叠）
  await selectTextEntity(page, 0, 0.02, 0.14, "城市");
  await selectTextEntity(page, 0, 0.3, 0.5, "人物");
  await expect(page.locator("[data-entity-id]")).toHaveCount(2, { timeout: 10_000 });

  // 3) span-click 打开实体编辑弹窗 → 应含「删除」按钮（删除二次确认入口）
  await page.locator("[data-entity-id]").first().click();
  const editDialog = page.locator(".el-dialog", { hasText: "编辑实体" });
  await expect(editDialog).toBeVisible({ timeout: 10_000 });
  await expect(editDialog.getByRole("button", { name: "删除" })).toBeVisible();
  await expect(editDialog.getByRole("button", { name: "保存" })).toBeVisible();
  await editDialog.getByRole("button", { name: "取消" }).click();
  await expect(editDialog).toBeHidden();

  // 4) 读取实体文本，用于关系选择
  const texts = await readEntityTexts(page);
  expect(texts.length).toBe(2);
  const [fromText, toText] = texts;

  // 5) 新建关系：终点候选被限制为与起点同句的实体；两端同句可创建
  await page.locator(".text-ner-bar").getByRole("button", { name: /新建/ }).click();
  const relDialog = page.locator(".el-dialog", { hasText: "新建关系" });
  await expect(relDialog).toBeVisible({ timeout: 10_000 });

  const items = relDialog.locator(".el-form-item");
  await pickSelectOption(page, items.nth(0).locator(".el-select"), fromText);
  // 起点选定后，终点下拉仅保留同一句的候选（排除起点自身）→ 恰好 1 项
  await items.nth(1).locator(".el-select").click();
  await expect(
    page.locator(".el-select-dropdown__item").filter({ visible: true })
  ).toHaveCount(1, { timeout: 6_000 });
  await pickSelectOption(page, items.nth(1).locator(".el-select"), toText);
  await pickSelectOption(page, items.nth(2).locator(".el-select"), "位于");
  await relDialog.getByRole("button", { name: "创建关系" }).click();
  await expect(relDialog).toBeHidden();
  await expect(page.locator(".text-ner-bar")).toContainText("关系（1）", { timeout: 10_000 });

  // 6) 保存
  await page.locator(".ann-footer").getByRole("button", { name: "保存" }).click();
  expect(savedAnnotations.length).toBeGreaterThanOrEqual(3);
  await page.screenshot({ path: shot("ner-final-2-saved.png") });

  // 7) 刷新验证持久化：实体与关系仍存在
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".text-ner-canvas .cm-editor").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("[data-entity-id]")).toHaveCount(2, { timeout: 15_000 });
  await expect(page.locator(".text-ner-bar")).toContainText("关系（1）", { timeout: 15_000 });
});
