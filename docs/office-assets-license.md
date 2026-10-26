# 办公 3D 场景角色资源 — 来源与许可清单

> 用途：为 `frontend/public/office/characters/` 提供 CC0 授权的、带骨骼与动画的模块化角色模型。
> 下载日期：**2026-10-25**（全部为当日实时下载；未改动任何应用代码）。

本次落地**两个包**：

| 包名 | 作者 | 许可 | 落地目录 | 文件数 | 体积 |
|------|------|------|----------|--------|------|
| KayKit Adventurers 2.0（FREE 档） | Kay Lousberg | CC0 1.0 | `frontend/public/office/characters/kaykit-adventurers/` | 14 | 3.76 MB |
| Blocky Characters 2.0 | Kenney | CC0 1.0 | `frontend/public/office/characters/kenney-blocky-characters/` | 38 | 2.34 MB |

合计 **52 个文件 / 6.10 MB**。

---

## 1. KayKit Adventurers 2.0（FREE 档）

- **来源页**：https://kaylousberg.itch.io/kaykit-adventurers
- **实际下载入口**：itch.io 免费下载流（页面 → `download_url` → `file/<upload_id>` → Cloudflare R2 签名直链），
  取得文件 `Free 2.0`（12 MB 压缩包）
- **作者**：Kay Lousberg（https://www.kaylousberg.com）
- **许可**：**CC0 1.0 Universal**（包内 `License.txt` 原文，逐字引用如下）

  ```
  KayKit : Adventurers Character Pack (2.0)
  Created/distributed by Kay Lousberg (www.kaylousberg.com)
  Creation date: 22/10/2025 09:00

  License: (Creative Commons Zero, CC0)
  http://creativecommons.org/publicdomain/zero/1.0/

  This content is free to use in personal, educational and commercial projects.
  ...
  If you wish to credit me you can do so by crediting "Kay Lousberg, www.kaylousberg.com" (this is not mandatory)
  ```

  itch 页面元数据同样标注 *Asset license: Creative Commons Zero v1.0 Universal*。
- **说明**：只取了 **FREE 档**内容；`EXTRA 2.0`（付费）与 `SOURCE 2.0`（付费）未下载、未使用。
- **包内文件清单**（相对 `frontend/public/office/characters/kaykit-adventurers/`）：

  ```
  License.txt                                1.5 KB   原始许可声明
  Characters/Barbarian.glb                 377.6 KB  野蛮人（含熊皮帽分件）
  Characters/Knight.glb                    333.7 KB  骑士（头盔/面罩/披风可拆）
  Characters/Mage.glb                      344.2 KB  法师（帽/披风分件）
  Characters/Ranger.glb                    473.4 KB  游侠（箭袋/披风分件）
  Characters/Rogue.glb                     399.6 KB  盗贼（披风分件）
  Characters/Rogue_Hooded.glb              372.5 KB  兜帽盗贼（兜帽/面罩分件）
  Characters/*_texture.png                 5 张       调色用贴图（glb 内已内嵌同一份，非运行时必需）
  Animations/Rig_Medium_General.glb        808.8 KB  15 个动作（Idle/Interact/PickUp/Death…）
  Animations/Rig_Medium_MovementBasic.glb  673.5 KB  11 个动作（Walking/Running/Jump…）
  ```

  （原包内的 `Assets/`（武器盾牌等 50+ 道具）、`Samples/`（渲染图）、`fbx/`、`obj/` 导出**未复制**，
  与本场景办公用途无关。若后续需要「手持物件」，可从同一 zip 的 `KayKit_Adventurers_2.0_FREE/Assets/gltf/` 取，
  许可相同。）

---

## 2. Kenney Blocky Characters 2.0

- **来源页**：https://kenney.nl/assets/blocky-characters
- **实际下载直链**：https://kenney.nl/media/pages/assets/blocky-characters/8369c0cf30-1749547469/kenney_blocky-characters_20.zip
- **作者**：Kenney（https://www.kenney.nl）
- **许可**：**CC0 1.0 Universal**（包内 `License.txt` 原文，逐字引用如下）

  ```
  Blocky Characters (2.0)
  Created/distributed by Kenney (www.kenney.nl)
  Creation date: 10-06-2025 11:19

  License: (Creative Commons Zero, CC0)
  http://creativecommons.org/publicdomain/zero/1.0/

  You can use this content for personal, educational, and commercial purposes.

  Support by crediting 'Kenney' or 'www.kenney.nl' (this is not a requirement)
  ```

- **包内文件清单**（相对 `frontend/public/office/characters/kenney-blocky-characters/`）：

  ```
  License.txt            原始许可声明
  Preview.png            18 个角色的外观总览（约 104 KB，纯参考图）
  character-a.glb … character-r.glb    18 个角色，每个约 110.9 KB
  Textures/texture-a.png … texture-r.png   18 张贴图，每张 12–22 KB
  ```

  ⚠️ **目录结构不能改**：每个 `character-*.glb` 内部以**相对路径**引用 `Textures/texture-*.png`
  （`images[0].uri = "Textures/texture-x.png"`），所以 `Textures/` 必须与 glb 同级，否则贴图 404、模型变白。
  （原包是 `Models/GLB format/` + 其下的 `Textures/`，这里已整体上提一层并保持相对关系。）

  （原包内的 FBX/OBJ 导出、`Overview.html`、`Previews/`、快捷方式 `.url` 文件**未复制**。）
- **授权层级**：Kenney 全站资产为 CC0，下载无需注册、无附加条款。

---

## 3. glb 技术摘要（Python 直接解析 glTF 头 + JSON chunk 实测）

### 3.1 KayKit（有骨骼 / skin，真骨骼蒙皮）

| 文件 | 大小 | skins | joints | 内嵌贴图 | 动画数 |
|------|------|-------|--------|----------|--------|
| Barbarian.glb | 377.6 KB | 1 | 23 | 1（bufferView） | 0 |
| Knight.glb | 333.7 KB | 1 | 23 | 1 | 0 |
| Mage.glb | 344.2 KB | 1 | 23 | 1 | 0 |
| Ranger.glb | 473.4 KB | 1 | 23 | 1 | 0 |
| Rogue.glb | 399.6 KB | 1 | 23 | 1 | 0 |
| Rogue_Hooded.glb | 372.5 KB | 1 | 23 | 1 | 0 |
| Rig_Medium_General.glb | 808.8 KB | 1 | 23 | 0 | **15** |
| Rig_Medium_MovementBasic.glb | 673.5 KB | 1 | 23 | 0 | **11** |

- **骨骼（23 个 joint，六个人物完全一致）**：
  `root, hips, spine, chest, upperarm.l/r, lowerarm.l/r, wrist.l/r, hand.l/r, handslot.l/r, head,
  upperleg.l/r, lowerleg.l/r, foot.l/r, toes.l/r`
  → 标准人形层级，带左右手 `handslot`（挂载点），命名统一为 `xxx.l` / `xxx.r`。
- **动作名（26 个，两个动画文件合计）**：
  - `Rig_Medium_General.glb`：`Death_A, Death_A_Pose, Death_B, Death_B_Pose, Hit_A, Hit_B,
    Idle_A, Idle_B, Interact, PickUp, Spawn_Air, Spawn_Ground, T-Pose, Throw, Use_Item`
  - `Rig_Medium_MovementBasic.glb`：`Jump_Full_Long, Jump_Full_Short, Jump_Idle, Jump_Land, Jump_Start,
    Running_A, Running_B, T-Pose, Walking_A, Walking_B, Walking_C`
  - ⚠️ **没有 `sit` 类坐姿动作**（坐姿在 KayKit 的其它/付费动画包里）。
- **角色节点（Knight 为例，33 个）**：
  `handslot.l, hand.l, wrist.l, lowerarm.l, upperarm.l, head, chest, spine, toes.r, foot.r, lowerleg.r,
  upperleg.r, toes.l, foot.l, lowerleg.l, upperleg.l, hips, root, Knight_ArmLeft, Knight_ArmRight,
  Knight_Body, Knight_Cape, Knight_Head, Knight_Helmet, Knight_HelmetVisor, Knight_LegLeft,
  Knight_LegRight, Rig_Medium`
- **分件（可换装）证据**：每个角色都是**同一套 23 骨骼下的多个 skinned mesh 分件**——
  `<名>_ArmLeft / _ArmRight / _Body / _Head / _LegLeft / _LegRight`，
  外加可选件 `_Cape`（6 个角色）、`_Helmet` + `_HelmetVisor`（Knight）、`_Hat`（Mage）、
  `_BearHat`（Barbarian）、`_Quiver`（Ranger）、`_Mask`（Rogue_Hooded）。
  因为骨骼完全同名，**A 角色的分件可以直接换到 B 角色的骨架上**（同 skin 索引），这是真正的模块化换装。
- **跨文件动作可复用（已实测校验）**：把 `Rig_Medium_General.glb` 所有动画通道引用的目标节点名
  与 `Knight.glb` 的节点名做集合比对，**缺失 0 个**（全部匹配）→ 在 three.js 里把动画 clip 交给
  角色自己的 `AnimationMixer` 即可按名绑定，无需 retarget、无需改骨骼。

### 3.2 Kenney Blocky（无骨骼 / 节点动画）

| 项 | 值（18 个文件全部一致） |
|----|------------------------|
| 大小 | 各 113,580 ~ 113,596 字节（约 110.9 KB） |
| skins | **0**（无蒙皮、无骨骼） |
| animations | **27 个** |
| 节点 | 8 个：`character-x, root, leg-left, leg-right, torso, arm-left, arm-right, head` |
| 贴图 | 外链 1 张：`Textures/texture-x.png`（**非内嵌**，见上文目录约束） |
| materials | 1 个：`texture-x` |

- **动作名（27 个，全部内嵌、名字与办公行为高度对应）**：
  `static, idle, walk, sprint, sit, drive, die, pick-up, emote-yes, emote-no, holding-right, holding-left,
  holding-both, holding-right-shoot, holding-left-shoot, holding-both-shoot, attack-melee-right,
  attack-melee-left, attack-kick-right, attack-kick-left, interact-right, interact-left,
  wheelchair-sit, wheelchair-move-forward, wheelchair-move-back, wheelchair-move-left, wheelchair-move-right`
- **「分件」是节点级而非蒙皮级**：`head / torso / arm-left / arm-right / leg-left / leg-right` 是 6 个
  独立 mesh 节点，动画靠父节点/子节点旋转（`root` 下挂腿、`torso` 上挂手臂与头）。
  因此**换装配色只能整贴图换**（同一 `.glb` 换 `Textures/texture-x.png`，或运行时 clone 后改
  `material.map`）；想「西装上衣 + 别的裤子」这种混搭做不到。

---

## 4. 许可结论

两个包均为 **CC0 1.0 Universal（公有领域贡献）**：

- 可商用、可修改、可再分发、**无需署名**；
- 包内原始 `License.txt` 已随包保留（`kaykit-adventurers/License.txt`、
  `kenney-blocky-characters/License.txt`），便于日后审计；
- 本项目若愿意，可在关于页/文档里致谢：`Kay Lousberg (kaylousberg.com)`、
  `Kenney (kenney.nl)`——纯自愿，非许可条件。

---

## 5. 与 `office3d.js` 的接入对照（**仅记录建议，未改任何代码**）

现有实现（`frontend/src/views/module_ai/office/office3d.js`）固定加载
`public/office/agent.glb`（**仓库里已存在**，本次未改动），并按 **动作名** 取片段：
`idle`、`walk`、`sit`（可选 `dance` / `sing`），手部挂点查找 `Hand.R` / `HandR`。

现有 `agent.glb` 实测（供对比基线）：1 个 skin / **17 joints**（`Hips, Spine, Chest, Neck, Head,
UpperArm.L/R, LowerArm.L/R, Hand.L/R, UpperLeg.L/R, LowerLeg.L/R, Foot.L/R`），
5 个动作 `dance, idle, sing, sit, walk`，29 个 mesh、材质按 **服装分件** 拆分
（`mat_shirt, mat_pants, mat_shoe, mat_hair, mat_skin, mat_eye, mat_accent`），
含 3 款发型（`hair_0 / hair_1 / hair_2` 及刘海、发髻子件）。

| 需求 | 现有 `agent.glb` | KayKit | Kenney Blocky |
|------|------------------|--------|---------------|
| 真骨骼 skin | ✅ 17 joints | ✅ 23 joints | ❌ skins = 0 |
| 单文件内含动作 | ✅ 5 个 | ❌ 动作在另外两个 glb | ✅ 27 个内嵌 |
| 动作名 `idle / walk / sit` 直接命中 | ✅ 逐字命中 | ❌（`Idle_A`、`Walking_A`，且无 sit） | ✅ `idle / walk / sit` 逐字命中 |
| 手部挂点 `Hand.R` | ✅ 存在 | `hand.r` + `handslot.r`（大小写/命名不同） | 仅 `arm-right` 节点 |
| 办公外观 | ✅ 衬衫/裤子/鞋/发型分件 | 奇幻（骑士/法师/盗贼…） | 现代（西装、白大褂、休闲装、工装，共 18 款） |
| 单角色体积 | 494.5 KB | 330–475 KB | 110.9 KB |

结论：**短期直接用现有 `agent.glb`**；Kenney 是「换风格 / 多角色外观」最省事的备选
（动作名逐字命中，但只改挂点命名、且换成节点动画）；KayKit 是唯一「真骨骼 + 大量动作 + 可换装分件」
的补充包，适合做 NPC/外部角色或后续重定向来源。

---

## 6. Quaternius（经 poly.pizza）

> 本节为 2026-10-25 追加，前五节的统计（52 个文件 / 6.10 MB）**不含**本节资源。

- **作者**：Quaternius（https://quaternius.com/，poly.pizza 作者页 https://poly.pizza/u/Quaternius）
- **为什么不经官网**：quaternius.com 的下载按钮跳 Google Drive，配额已超限（无法取得文件）。
  poly.pizza 收录了同一批 CC0 模型并提供**静态直链**，故改走此处。
- **实际下载入口（三段式）**：
  1. `GET https://poly.pizza/api/model/<PublicID>/details` → 返回 `ResourceID`（UUID）
  2. `GET https://static.poly.pizza/<ResourceID>.glb` → `200`，`content-type: gltf-binary`
  3. 无需登录、无验证码、无 redirect 到网盘（本次 7 个文件**首次请求全部 200**，无失败重试）
- **注意（下次抓取可省时间）**：`/m/<id>` 这类 HTML 页面对 Node 的 `fetch` 会返回 **Cloudflare 403
  “Just a moment...”**，但 `curl.exe` 与 `/api/**` 均正常；**不要用网页 HTML 找直链**，
  直接走上面的 `details` 接口 + `static.poly.pizza` 更稳。

- **来源页**：
  - Ultimate Modular Men Pack：https://poly.pizza/bundle/Ultimate-Modular-Men-Pack-ZiH8muWqwQ
  - Ultimate Modular Women Pack：https://poly.pizza/bundle/Ultimate-Modular-Women-Pack-aCBDXDdTNN
  - 单模型页统一为 `https://poly.pizza/m/<PublicID>`
- **落地目录**：`frontend/public/office/characters/quaternius/`（7 个 glb + README.md，共 **9.65 MB**）

### 6.1 许可结论

6 个角色（男性模块包 5 个 + 女性包 1 个）为 **CC0 1.0**；素模 `base-rig-animated.glb` 是
**CC-BY 3.0**（poly.pizza 标注，需要署名），**不属于 CC0**，仅作动作源，未用于默认角色外观。

poly.pizza 接口返回的许可字段（原文，逐字）：

```json
// 男性包 / 女性包成员（casual_character、hoodie_character、business_man、
// beach_character、worker、woman_casual）
"Licence": "CC0 1.0"
```

```json
// base-rig-animated.glb（"Animated Base Character"）
"Licence": "CC-BY 3.0"
```

bundle 描述原文（逐字，说明商用与格式）：

```
11 Different characters with 24 animations! Each character is divided into 4 models that can be
swapped to create new combinations. In FBX + GLB formats, free to use in personal and commercial projects
```

```
10 Different characters with 24 animations! Each character is divided into 4 models that can be swapped
to create new combinations, humanoid rig version also included. In FBX + GLB formats, free to use in
personal and commercial projects
```

- CC0 部分：可商用、可修改、无需署名（本项目仍在本文档致谢 `Quaternius`）。
- CC-BY 部分（素模）：如对外分发需署名 **“Quaternius (quaternius.com)”**，并注明 CC-BY 3.0。

### 6.2 文件与实测（glTF JSON chunk 解析）

| 文件 | 角色 | PublicID | 大小 | skins | joints | 动画 | 贴图 |
|------|------|----------|------|-------|--------|------|------|
| `casual_character.glb` | 灰 T 恤 + 牛仔裤 + 红球鞋 | `kZ3DmIoGip` | 1.36 MB | 4 | 62 | 24 | 无（0 images） |
| `hoodie_character.glb` | 紫卫衣 + 短裤 | `gKLBoRsyKe` | 1.39 MB | 4 | 62 | 24 | 无 |
| `business_man.glb` | 西装 + 领带 | `JFrLIKqvCH` | 1.46 MB | 4 | 62 | 24 | 无 |
| `beach_character.glb` | T 恤 + 短裤 + 耳钉 | `DojKLcO34E` | 1.44 MB | 4 | 62 | 24 | 无 |
| `worker.glb` | 安全帽 + 反光背心 | `Yg2bQZO6Hj` | 1.28 MB | 4 | 62 | 24 | 无 |
| `woman_casual.glb` | 女，T 恤 + 长裤 | `jpKRgGDxhk` | 0.56 MB | 1 | 31 | 11 | 无 |
| `base-rig-animated.glb` | 素模（无服装/五官） | `cwYvO5UauX` | 2.16 MB | 1 | 53 | 45 | 无 |

- 生成器均为 `FBX2glTF v0.9.7`；`images = 0`，颜色写在材质 `baseColorFactor` 上 → **单文件自包含**。
- 尺度（three.js GLTFLoader 实测 bbox）：男性 5 个 1.82–1.84 单位高、脚底 y≈0、`scale=1` 可用；素模 1.78；
  **`woman_casual.glb` 为 4.64 单位高**（根节点 `HumanArmature` / `Female` 均 `scale=100`），
  放进场景需 `scale≈0.4` 才能与男性同高。全部 Y-up、面朝 +Z（glTF 规范默认）。
- 已用 `three@0.170.0` 的 `GLTFLoader.parse` 逐个真机加载：**7/7 成功**，动画数与上表一致；
  `isSkinnedMesh` 数量为 10–13 个（glTF 每个 `mesh` 的多 primitive 被按材质拆开），
  换装请按 `*_Head / *_Body / *_Legs / *_Feet` 前缀分组。
- 男性包每个文件是 **4 个 glTF mesh**（`skins = 4`，各自一条 62 关节骨架副本；three.js 加载后
  再按材质拆成 10–13 个 `SkinnedMesh`）：
  `<名>_Head`（头/发/眉/眼）、`<名>_Body`（上衣）、`<名>_Legs`（裤）、`<名>_Feet`（鞋）——
  即 bundle 说的“每角色 4 个可换装分件”。
- 骨骼链：`Root → Hips → Abdomen → Torso → Chest → Neck → Head`；
  `Shoulder → UpperArm → LowerArm → Wrist → Index/Middle/Ring/Pinky/Thumb(1-4)`；
  `UpperLeg → LowerLeg → Foot → PT`。
- **手部挂点**：男性包 **`Wrist.R`**（无 `Hand.R`）；女性包 `Palm.R` + `MiddleHand.R`；素模 `DEF-hand.R`。

### 6.3 动作名（最关键）

男性模块包（24 个，**全部带 `CharacterArmature|` 前缀**）：

```
Idle, Idle_Neutral, Idle_Gun, Idle_Gun_Pointing, Idle_Gun_Shoot, Idle_Sword,
Walk, Run, Run_Back, Run_Left, Run_Right, Run_Shoot,
Interact, Wave, Gun_Shoot, Sword_Slash,
Punch_Left, Punch_Right, Kick_Left, Kick_Right, Roll,
HitRecieve, HitRecieve_2, Death
```

女性包单文件（11 个，前缀 `HumanArmature|`）：

```
Female_Clapping, Female_Death, Female_Idle, Female_Jump, Female_Punch, Female_Run,
Female_RunningJump, Female_Sitting, Female_Standing, Female_SwordSlash, Female_Walk
```

素模（45 个，前缀 `Rig|`，节选关键项）：

```
Idle_Loop, Idle_Talking_Loop,
Walk_Loop, Walk_Formal_Loop, Jog_Fwd_Loop, Sprint_Loop,
Sitting_Enter, Sitting_Idle_Loop, Sitting_Exit, Sitting_Talking_Loop,
Dance_Loop, Interact, Push_Loop, Driving_Loop, Fixing_Kneeling, PickUp_Table,
Jump_Start, Jump_Loop, Jump_Land, Swim_Fwd_Loop, Swim_Idle_Loop, Crouch_Idle_Loop, ...
```

| 需求 | 男性模块包（CC0） | 女性包（CC0） | 素模（CC-BY） |
|------|-------------------|---------------|----------------|
| Idle | ✅ `Idle` / `Idle_Neutral` | ✅ `Female_Idle` | ✅ `Idle_Loop` |
| Walk | ✅ `Walk` | ✅ `Female_Walk` | ✅ `Walk_Loop` |
| Run | ✅ `Run` | ✅ `Female_Run` | ✅ `Jog_Fwd_Loop` / `Sprint_Loop` |
| **Sit** | ❌ 无 | ✅ `Female_Sitting`（无 Enter/Exit） | ✅ `Sitting_Enter/Idle_Loop/Exit` |
| **Dance** | ❌ 无 | ❌ 无 | ✅ `Dance_Loop` |
| **Cheer** | ❌ 无（可用 `Wave` 近似） | ⚠️ `Female_Clapping` 近似 | ❌ 无 |
| **Talk** | ❌ 无（`Interact` 近似） | ❌ 无 | ✅ `Idle_Talking_Loop` / `Sitting_Talking_Loop` |

**结论**：想要“现代休闲外观 + 真骨骼 + 24 动作”，用男性/女性模块包（CC0）；
但 **Sit / Dance / Talk 只有素模 `base-rig-animated.glb` 才有**，而它外观是素模、不适合直接展示。
可行组合：用模块包角色做显示 + 从素模提取动作做重定向（两套骨架关节数不同：62 vs 53，
需手工映射或用 three.js `SkeletonUtils.retarget`，`Wrist.R ↔ DEF-hand.R`）。
女性 `woman_casual.glb` 是**唯一同时具备现代休闲外观与 `Sitting` 动作的 CC0 角色**，
若只需“坐着办公”这一姿态，优先用它。

### 6.4 对现有 `agent.glb` 的补充价值

| 维度 | `agent.glb` | Quaternius 模块包 |
|------|-------------|-------------------|
| 外观 | 衬衫/裤/鞋/发型分件 | 休闲 T 恤、卫衣、西装、工装、海滩装（6 套） |
| 骨骼 | 17 joints | 62 joints（含五指） |
| 动作 | 5 个（dance/idle/sing/sit/walk） | 24 个（含 Idle/Walk/Run/Interact/Wave，**无 sit/dance/sing**） |
| 手部挂点 | `Hand.R` | `Wrist.R` |
| 换装 | 材质与 mesh 分件 | 4 个独立 skinned mesh（Head/Body/Legs/Feet）可拆换 |

即：**外观与骨骼精度更强，但“坐/跳舞/说话”反而不如现有 `agent.glb` 全**，
适合做“多外观 NPC/同事”，不适合完全替代 `agent.glb`。

> 备注：本次仅新增 `frontend/public/office/characters/quaternius/**` 与本文件，未改动
> `office3d.js` / `index.vue` 等任何应用代码。
