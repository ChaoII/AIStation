// 场景（Scenario）功能端到端证明：接线完成后，场景从"空转"变成真的可用。
//
// 修前：后端沙箱写好了，但**没有任何入口能产生场景编辑** ⇒ 建场景、看 diff、
// 点合并，编辑数永远是 0，点合并必返回"该场景没有任何可合并的编辑"。
// 本用例走完整 HTTP 链路证明它真的活了：
//   建场景 → 场景内执行动作（只暂存）→ 编辑数>0 → 真实表未被污染 → 合并 → 真实表变化
import { test, expect } from "@playwright/test";

import { login } from "./anno-helper";

const API = process.env.E2E_API_URL || "http://127.0.0.1:8002/api/v1";
const OBJ = "video_cameras";
const KEY = "1";

test("场景：场景内编辑只暂存，合并后才落到真实表", async ({ request }) => {
  const headers = await login(request);
  let sc = `sc_e2e_${Date.now()}`;
  const act = `e2e_sc_action_${Date.now()}`;
  const before = `基线名${Date.now() % 1000}`;

  // 0) 造一个可执行的动作（打在真实表上，非场景时会真写）
  const save = await request.post(`${API}/ai/ontology/action/save`, {
    headers,
    data: {
      object_code: OBJ, name: "e2e场景动作", code: act,
      target_table: OBJ, approval: false, white_fields: ["name"],
      rules: [{ type: "modify_object",
                assignments: [{ property: "name", source: "parameter", value: "name" }] }],
    },
  });
  expect(save.ok(), "建动作应成功").toBeTruthy();

  // 先把目标行置成已知值，确保后续 diff 可判定
  const seed = await request.post(`${API}/ai/ontology/action/execute`, {
    headers,
    data: { code: act, object_key: KEY, params: { name: before } },
  });
  expect(seed.ok(), "置基线值应成功").toBeTruthy();

  try {
    // 1) 建场景（注意：带 code 是"更新"，新建必须不传 code，由后端生成）
    const mk = await request.post(`${API}/ai/ontology/scenario/save`, {
      headers, data: { name: `e2e场景${sc}`, ttl_days: 7 },
    });
    const mkBody = await mk.json();
    expect(mk.ok(), `建场景失败：${JSON.stringify(mkBody)}`).toBeTruthy();
    const scen = mkBody?.data?.code;
    expect(scen, `后端未返回场景编码：${JSON.stringify(mkBody)}`).toBeTruthy();
    sc = String(scen);

    // 2) 场景内执行 → 必须只暂存、不写真实表
    const inScn = await request.post(`${API}/ai/ontology/action/execute`, {
      headers,
      data: { code: act, object_key: KEY, params: { name: "场景内改名" }, scenario: sc },
    });
    const d = (await inScn.json()).data;
    expect(d.ok, `场景内执行失败：${JSON.stringify(d)}`).toBeTruthy();
    expect(d.staged, "场景内执行必须是暂存（不写真实表）").toBeTruthy();

    // 3) 编辑数必须 > 0 —— 修前这里永远是 0（功能空转的直接证据）
    const detail = await (
      await request.get(`${API}/ai/ontology/scenario/${encodeURIComponent(sc)}`, { headers })
    ).json();
    expect(detail.data?.edit_count, "场景编辑数应大于 0").toBeGreaterThan(0);

    // 4) 真实表此刻仍是基线值（沙箱没漏写）
    const inst = await (
      await request.get(`${API}/ai/ontology/instance/${OBJ}/${KEY}`, { headers })
    ).json();
    expect(inst.data?.props?.name, "场景内执行污染了真实表").toBe(before);

    // 5) 合并 → 真实表变成场景值
    const apply = await request.post(`${API}/ai/ontology/scenario/apply`, {
      headers, data: { code: sc },
    });
    const a = (await apply.json()).data;
    expect(a.ok, `合并失败：${JSON.stringify(a)}`).toBeTruthy();

    const after = await (
      await request.get(`${API}/ai/ontology/instance/${OBJ}/${KEY}`, { headers })
    ).json();
    expect(after.data?.props?.name, "合并后真实表没有更新").toBe("场景内改名");
  } finally {
    // 还原基线值 + 清理动作与场景
    await request.post(`${API}/ai/ontology/action/execute`, {
      headers, data: { code: act, object_key: KEY, params: { name: before } },
    }).catch(() => undefined);
    await request.post(`${API}/ai/ontology/scenario/remove`, {
      headers, data: { code: sc },
    }).catch(() => undefined);
    await request.post(`${API}/ai/ontology/remove`, {
      headers, params: { kind: "action", id: 0 },
      data: { code: act },
    }).catch(() => undefined);
  }
});
