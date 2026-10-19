// 个人工作空间（/ai/space）活系统冒烟：设计文档的接线此前只有静态核查、无 e2e 覆盖。
//
// 验证设计的成功标准里可被 UI 观测的部分：
//   · 菜单可达 → 页面渲染 → 配额可见（used/quota/max_file）
//   · 文件夹树与上传入口存在（全链路的入口侧）
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";

test("个人工作空间：页面可达且配额/文件夹树渲染", async ({ page, request }) => {
  const headers = await login(request);

  // 接口侧：配额接口可用且字段齐全
  const q = await (await request.get(`${API}/ai/space/quota`, { headers })).json();
  expect(q.success, `配额接口失败：${JSON.stringify(q)}`).toBeTruthy();
  expect(q.data, "配额缺少字段").toMatchObject({
    used_bytes: expect.anything(),
    quota_bytes: expect.anything(),
    max_file_bytes: expect.anything(),
  });

  // 页面侧：路由可达且主容器渲染
  await page.addInitScript(() => {
    localStorage.setItem("guideVisible", "false");
    localStorage.setItem("showGuide", "false");
  });
  await page.goto("/#/ai/space", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".app-main .app-container").first()).toBeVisible({
    timeout: 20_000,
  });
  // 配额/新建入口要在页面上可见（"前端可见"是成功标准之一）
  await expect(page.getByRole("button", { name: /新建|上传/ }).first()).toBeVisible({
    timeout: 15_000,
  });

  // 配额必须**真的渲染出后端下发的值**，而不是停在初值 1B。
  // （`quotaTotal` 的兜底初值是 1，若 loadQuota 失败/未完成就会显示 "0 B / 1 B"）
  const quotaText = page.locator(".space-quota-text");
  await expect(quotaText).toBeVisible({ timeout: 15_000 });
  await expect(quotaText, "配额没有渲染出后端值（仍是初值 1B）").not.toHaveText(/\/\s*1\s*B$/, {
    timeout: 15_000,
  });
  await expect(quotaText).toHaveText(/\/\s*\d+(\.\d+)?\s*(B|KB|MB|GB|TB)$/, {
    timeout: 15_000,
  });
  await page.screenshot({ path: "e2e/personal-space.png" });
});

// 写路径闭环：上传 → 列表可查 → 下载内容一致 → 配额计入 → 删除 → 配额归零。
// 这条覆盖的是"接线是否真的通"（而不是页面能不能打开），失败会留下脏数据，故用 finally 清理。
test("个人工作空间：上传→列表→下载→配额→删除 闭环", async ({ request }) => {
  const headers = await login(request);
  const quota = async () => {
    const r = await (await request.get(`${API}/ai/space/quota`, { headers })).json();
    expect(r.success, `配额接口失败：${JSON.stringify(r)}`).toBeTruthy();
    return r.data as { used_bytes: number; quota_bytes: number; max_file_bytes: number };
  };

  const before = await quota();
  const name = `e2e-空间冒烟-${Date.now()}.txt`;
  const content = "个人工作空间 e2e 闭环验证\n";

  let fileId = 0;
  try {
    const up = await (
      await request.post(`${API}/ai/space/files/upload`, {
        headers,
        multipart: {
          file: { name, mimeType: "text/plain", buffer: Buffer.from(content, "utf-8") },
        },
      })
    ).json();
    expect(up.success, `上传失败：${JSON.stringify(up)}`).toBeTruthy();
    fileId = up.data.id;
    expect(fileId, "上传未返回文件 id").toBeGreaterThan(0);

    // 列表里能查到（证明落库 + 归属当前用户）
    const list = await (
      await request.get(`${API}/ai/space/files/list`, {
        headers,
        params: { keyword: name, page_no: 1, page_size: 20 },
      })
    ).json();
    expect(list.success, `列表失败：${JSON.stringify(list)}`).toBeTruthy();
    expect(
      (list.data.items as Array<{ id: number }>).some((f) => f.id === fileId),
      "刚上传的文件没出现在列表里"
    ).toBe(true);

    // 下载内容与上传一致
    const dl = await request.get(`${API}/ai/space/files/${fileId}/download`, { headers });
    expect(dl.ok(), `下载失败：HTTP ${dl.status()}`).toBeTruthy();
    expect(await dl.text()).toBe(content);

    // 配额计入（used_bytes 增加、且不超过总量）
    const afterUpload = await quota();
    expect(afterUpload.used_bytes, "上传后配额没有增加").toBeGreaterThan(before.used_bytes);
    expect(afterUpload.used_bytes).toBeLessThanOrEqual(afterUpload.quota_bytes);
  } finally {
    if (fileId) {
      const del = await (
        await request.delete(`${API}/ai/space/files/delete`, { headers, data: [fileId] })
      ).json();
      expect(del.success, `清理失败（请手工删除 ${name}）：${JSON.stringify(del)}`).toBeTruthy();
    }
  }

  // 删除后配额回落，且列表查不到
  const afterDelete = await quota();
  expect(afterDelete.used_bytes, "删除后配额没有回落").toBe(before.used_bytes);
  const listAfter = await (
    await request.get(`${API}/ai/space/files/list`, {
      headers,
      params: { keyword: name, page_no: 1, page_size: 20 },
    })
  ).json();
  expect(
    (listAfter.data.items as Array<{ id: number }>).some((f) => f.id === fileId),
    "删除后文件仍出现在列表里"
  ).toBe(false);
});
