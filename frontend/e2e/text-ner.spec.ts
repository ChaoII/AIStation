import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test, expect, type Page, type Route } from "@playwright/test";

// 文本 NER 工作台端到端（前端隔离验证）：拦截 annotation 接口，物料化一个 text_ner 任务，
// 验证 CodeMirror 只读拖选生成实体、实体/关系编辑、保存与持久化。
// 对应 Task 7 遗留的 DOM 层验证清单（拖选可用、span-click 可达、color-mix 高亮）。

const TEXT = readFileSync(fileURLToPath(new URL("./fixtures/sample.txt", import.meta.url)), "utf-8");
const SHOT = "C:/Users/aichao/AppData/Local/Temp/opencode";

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

test("文本 NER 工作台：拖选生成实体、创建关系、保存与持久化", async ({ page }) => {
  savedAnnotations = [];

  await page.route("**/api/v1/annotation/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/detail") && path.includes("/task/")) {
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
    if (path.includes("/document/content/")) {
      return route.fulfill({ contentType: "text/plain; charset=utf-8", body: TEXT });
    }
    if (path.endsWith("/document/lock/") || /\/document\/lock\/\d+$/.test(path)) {
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
      const body = route.request().postDataJSON();
      savedAnnotations = body?.annotations || [];
      return json(route, {
        code: 0,
        msg: "保存成功",
        data: { version: 2, annotation_count: savedAnnotations.length },
      });
    }
    return route.continue();
  });

  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto(`/#/annotation/workbench/1`, { waitUntil: "domcontentloaded" });
  await expect(page.locator(".text-ner-canvas .cm-editor").first()).toBeVisible({ timeout: 20_000 });

  // 1) 加载：文档全文渲染 + 截图
  await expect(page.locator(".text-ner-canvas .cm-content .cm-line").first()).toBeVisible();
  await page.screenshot({ path: `${SHOT}/ner-1-loaded.png` });
  await expect(page.locator(".text-ner-bar")).toBeVisible();

  const editor = page.locator(".text-ner-canvas .cm-editor .cm-content");
  async function dragSelect(lineIdx: number, fromFrac: number, toFrac: number) {
    const line = editor.locator(".cm-line").nth(lineIdx);
    await line.scrollIntoViewIfNeeded();
    // 文本实际宽度可能远窄于 .cm-line 的整行盒（中文较短），若按行盒百分比会拖到文字右侧空白。
    // 因此用 Range 量测该行的文字外接矩形，按其宽度计算百分比坐标。
    const textRect = await line.evaluate((el) => {
      const r = document.createRange();
      r.selectNodeContents(el);
      const rect = r.getBoundingClientRect();
      return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
    });
    const y = textRect.y + textRect.h / 2;
    await page.mouse.move(textRect.x + textRect.w * fromFrac, y);
    await page.mouse.down();
    await page.waitForTimeout(120);
    await page.mouse.move(textRect.x + textRect.w * toFrac, y, { steps: 20 });
    await page.waitForTimeout(80);
    await page.mouse.up();
  }

  // 2) 拖选生成实体 1（验证 readOnly/editable=false 仍可拖选）
  await dragSelect(0, 0.04, 0.2);
  const entityDialog = page.locator(".el-dialog", { hasText: "选择实体类型" });
  await expect(entityDialog).toBeVisible({ timeout: 10_000 });
  await entityDialog.locator("button", { hasText: "确定" }).click();
  await expect(page.locator("[data-entity-id]").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.locator(".text-ner-canvas .cm-line span.text-ner-entity").first()).toBeVisible();
  await page.screenshot({ path: `${SHOT}/ner-2-entity.png` });

  // 2b) 再拖选一个实体（同句、无重叠）
  // 上次实体对话框关闭时遮罩会残留瞬间，可能吞掉拖选的 mousedown；先让其完全移除。
  await page.waitForTimeout(800);
  await dragSelect(0, 0.3, 0.8);
  await expect(page.locator(".el-dialog", { hasText: "选择实体类型" })).toBeVisible({ timeout: 10_000 });
  await page.locator(".el-dialog", { hasText: "选择实体类型" }).locator("button", { hasText: "确定" }).click();
  await expect(page.locator("[data-entity-id]")).toHaveCount(2, { timeout: 10_000 });

  // 2c) 点击实体 → 打开编辑对话框（span-click 验证）
  await page.locator("[data-entity-id]").first().click();
  await expect(page.locator(".el-dialog", { hasText: "编辑实体" })).toBeVisible({ timeout: 10_000 });
  await page.locator(".el-dialog", { hasText: "编辑实体" }).locator("button", { hasText: "取消" }).click();

  // 3) 新建关系（两端实体同句）
  await page.locator(".text-ner-bar").getByRole("button", { name: /新建/ }).click();
  const relDialog = page.locator(".el-dialog", { hasText: "新建关系" });
  await expect(relDialog).toBeVisible({ timeout: 10_000 });
  const items = relDialog.locator(".el-form-item");
  async function pickOption(selectLocator: any, index: number) {
    await selectLocator.click();
    // 下拉列表带过渡动画，用 visible 过滤 + force 点击规避“not stable”误报。
    await page.waitForTimeout(400);
    await page
      .locator(".el-select-dropdown__item")
      .filter({ visible: true })
      .nth(index)
      .click({ force: true });
    await page.waitForTimeout(200);
  }
  await pickOption(items.nth(0).locator(".el-select"), 0);
  await pickOption(items.nth(1).locator(".el-select"), 1);
  await pickOption(items.nth(2).locator(".el-select"), 0);
  await relDialog.locator("button", { hasText: "创建关系" }).click();
  await expect(page.locator(".text-ner-bar").getByText("关系（1）")).toBeVisible({ timeout: 10_000 });
  // 关系项默认在折叠区里，先展开「关系」区；关系项是含「位于」或箭头的一项。
  await page.locator(".text-ner-bar .tacc-head").filter({ hasText: "关系" }).click();
  await page.locator(".text-ner-bar .titem").filter({ hasText: "位于" }).first().hover();
  await expect(page.locator(".text-ner-entity--selected")).toHaveCount(2, { timeout: 10_000 });
  await page.screenshot({ path: `${SHOT}/ner-3-relation.png` });

  // 4) 保存
  await page.locator(".ann-footer").getByRole("button", { name: "保存" }).click();
  expect(savedAnnotations.length).toBeGreaterThanOrEqual(2);
  await page.screenshot({ path: `${SHOT}/ner-4-saved.png` });

  // 5) 刷新验证持久化
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.locator(".text-ner-canvas .cm-editor").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("[data-entity-id]")).toHaveCount(2, { timeout: 15_000 });
  await expect(page.locator(".text-ner-bar").getByText("关系（1）")).toBeVisible({ timeout: 15_000 });
});
