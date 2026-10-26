# Quaternius 角色（经 poly.pizza，CC0）

> 抓取日期：2026-10-25。全部为 `.glb`（glTF 2.0 二进制），**无外部贴图依赖**。
> 来源：poly.pizza 收录的 Quaternius 模型（Quaternius 官网下载走 Google Drive，配额已超限）。

## 文件

| 文件 | 角色 | 体积 | skins / joints | 动画数 | 许可 |
|------|------|------|----------------|--------|------|
| `casual_character.glb` | 休闲男（灰 T 恤 + 牛仔裤 + 红球鞋） | 1.36 MB | 4 / 62 | 24 | CC0 1.0 |
| `hoodie_character.glb` | 休闲男（紫卫衣 + 短裤） | 1.39 MB | 4 / 62 | 24 | CC0 1.0 |
| `business_man.glb` | 商务男（深色西装 + 领带） | 1.46 MB | 4 / 62 | 24 | CC0 1.0 |
| `beach_character.glb` | 休闲男（T 恤 + 短裤 + 耳钉） | 1.44 MB | 4 / 62 | 24 | CC0 1.0 |
| `worker.glb` | 工装男（安全帽 + 反光背心 + 胡子） | 1.28 MB | 4 / 62 | 24 | CC0 1.0 |
| `woman_casual.glb` | 休闲女（T 恤 + 长裤） | 0.56 MB | 1 / 31 | 11 | CC0 1.0 |
| `base-rig-animated.glb` | **人体素模**（黄紫分段，无服装无五官） | 2.16 MB | 1 / 53 | **45** | **CC-BY 3.0** |

前 6 个来自 **Ultimate Modular Men / Women Pack**（每角色 4 个可换装分件、24 个动作）；
`base-rig-animated.glb` 是**动作库/重定向源**，外观是素模、不适合直接当办公角色显示。

## 动作（男性模块包，24 个，名字带前缀）

```
CharacterArmature|Idle              CharacterArmature|Idle_Neutral
CharacterArmature|Walk              CharacterArmature|Run
CharacterArmature|Run_Back          CharacterArmature|Run_Left
CharacterArmature|Run_Right         CharacterArmature|Run_Shoot
CharacterArmature|Idle_Gun          CharacterArmature|Idle_Gun_Pointing
CharacterArmature|Idle_Gun_Shoot    CharacterArmature|Idle_Sword
CharacterArmature|Gun_Shoot         CharacterArmature|Sword_Slash
CharacterArmature|Interact          CharacterArmature|Wave
CharacterArmature|Punch_Left        CharacterArmature|Punch_Right
CharacterArmature|Kick_Left         CharacterArmature|Kick_Right
CharacterArmature|Roll              CharacterArmature|HitRecieve
CharacterArmature|HitRecieve_2      CharacterArmature|Death
```

**没有** `Sit` / `Dance` / `Cheer` / `Talk`。女性单角色另有 `Female_Sitting`、`Female_Clapping`。

素模 `base-rig-animated.glb`（45 个）补齐了缺口：
`Rig|Idle_Loop`、`Rig|Idle_Talking_Loop`、`Rig|Sitting_Enter / Sitting_Idle_Loop / Sitting_Exit`、
`Rig|Sitting_Talking_Loop`、`Rig|Dance_Loop`、`Rig|Walk_Loop`、`Rig|Walk_Formal_Loop`、`Rig|Jog_Fwd_Loop`、
`Rig|Sprint_Loop`、`Rig|Interact`、`Rig|Push_Loop`、`Rig|Driving_Loop`、`Rig|Fixing_Kneeling` 等。

## 骨骼与分件

- 男性包：`Root → Hips → Abdomen → Torso → Chest → Neck → Head`，手臂 `Shoulder → UpperArm → LowerArm → Wrist → 五指`，
  腿 `UpperLeg → LowerLeg → Foot → PT`（**62 joints**，每文件 4 条相同骨架副本）。
- **没有 `Hand.R`**；手部根骨是 **`Wrist.R`**（另有 `Wrist.L`），手指骨 `Index1-4.R / Middle / Ring / Pinky / Thumb`。
- 女性包：手部根骨 `Palm.R`，并有 `MiddleHand.R`（**31 joints**）。
- 素模：`root → DEF-hips → DEF-spine.001-003 → DEF-neck → DEF-head`，手骨 **`DEF-hand.R`**（53 joints）。
- 每个男性角色是 4 个逻辑分件（glTF `mesh`，three.js 再按材质拆成 10–13 个 `SkinnedMesh`），可单独换装：
  `*_Head`（头/发/眉/眼）、`*_Body`（上衣）、`*_Legs`（裤）、`*_Feet`（鞋）。

## 零贴图

7 个文件 `images = 0`：颜色全部写在材质的 `pbrMetallicRoughness.baseColorFactor` 上，
所以**不存在贴图丢失或 404 问题**，单文件即自包含。

## 尺度（实测 bbox，three.js GLTFLoader 实际加载）

| 文件 | 身高（Y） | 脚底 | 备注 |
|------|-----------|------|------|
| 男性 5 个 | 1.82–1.84 | y≈0 | `scale=1` 直接用 |
| `base-rig-animated.glb` | 1.78 | y≈0 | `scale=1` |
| `woman_casual.glb` | **4.64** | y≈0 | 根节点 `HumanArmature` / `Female` 均为 `scale=100`，**需 `scale≈0.4`** 才能与男性同高 |

模型均为 Y-up、**面朝 +Z**（glTF 规范默认朝向），与 three.js 默认相机方向一致；无需额外旋转。

> 逻辑上是 4 个分件（glTF `mesh`），但 three.js 会按材质把多 primitive 的 mesh 拆开，
> 因此加载后 `isSkinnedMesh` 数量为 **10–13 个**（`*_Head` / `*_Body` / `*_Legs` / `*_Feet` 的多个子网格），
> 换装时应按名字前缀分组，而不是按「4 个对象」硬编码。
