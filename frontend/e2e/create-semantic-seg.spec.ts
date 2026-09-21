import { test, expect, type Page, type APIRequestContext } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：语义分割（逐点 + 双击闭合 + 填充背景，含「覆盖已有背景」保护）创建流程。

const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const BG_CLASS_ID = 1001;
const BG_CLASS_NAME = "背景类";

async function getImageId(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: number
): Promise<number> {
  const dRes = await request.get(`${API}/annotation/task/${taskId}/detail`, { headers: auth });
  expect(dRes.ok()).toBeTruthy();
  const datasetId = (await dRes.json()).data.dataset_id;
  const imgRes = await request.get(`${API}/annotation/dataset/${datasetId}/images?task_id=${taskId}`, {
    headers: auth,
  });
  expect(imgRes.ok()).toBeTruthy();
  const items = (await imgRes.json()).data.items;
  expect(items?.length).toBeGreaterThan(0);
  return Number(items[0].id);
}

async function getAnnotations(
  request: APIRequestContext,
  auth: Record<string, string>,
  taskId: number,
  imageId: number
): Promise<any[]> {
  const res = await request.get(
    `${API}/annotation/anno/image/${imageId}/annotations?task_id=${taskId}`,
    { headers: auth }
  );
  expect(res.ok()).toBeTruthy();
  return (await res.json()).data || [];
}

test("semantic_segmentation 画多边形 + 填充背景生成标注", async ({ page, request }) => {
  const auth = await login(request);
  // 给任务挂一个背景类别，避免面板 el-select 为空导致「填充背景」不可用
  const taskId = await createAnnotationTask(request, auth, "semantic_segmentation", "semseg", [
    { id: BG_CLASS_ID, name: BG_CLASS_NAME, color: "#909399" },
  ]);
  await gotoWorkbench(page, taskId);

  // 切到多边形工具（快捷键 p）
  await page.keyboard.press("p");

  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);
  // 双击闭合
  await page.mouse.dblclick(img.x + img.width * 0.6, img.y + img.height * 0.7);

  await expectAnnotation(page);

  // 选择背景类别（面板 el-select），选中后「填充背景」应可用
  await page.locator(".seg-panel .el-select").click();
  await page.getByRole("option", { name: BG_CLASS_NAME }).click();
  const fillBtn = page.locator(".seg-panel button", { hasText: "填充背景" });
  await expect(fillBtn).toBeEnabled();

  // 点击「填充背景」并确认对话框
  await fillBtn.click();
  await page.locator(".el-message-box").getByRole("button", { name: "填充" }).click();
  await expect(page.locator(".el-message-box")).toHaveCount(0);

  // 再次填充：应弹出「覆盖已有背景」确认框并允许覆盖（校验重复守卫不失效）
  await fillBtn.click();
  await page.locator(".el-message-box").getByRole("button", { name: "覆盖" }).click();
  await expect(page.locator(".el-message-box")).toHaveCount(0);

  // 保存当前图（Ctrl+S），经接口断言背景标注（class_id=BG_CLASS_ID）已落库且仅一份（覆盖后无重复）
  await page.keyboard.press("Control+s");
  const imageId = await getImageId(request, auth, taskId);
  await expect
    .poll(async () => {
      const anns = await getAnnotations(request, auth, taskId, imageId);
      return anns.filter((a) => a.class_id === BG_CLASS_ID).length;
    })
    .toBe(1);
});
