// AI 办公室 · Three.js 场景（数据驱动）
// 说明：场景/材质/人物都是程序化生成的，agent 数量变化只影响「座位分配 + 名牌密度」
/* eslint-disable */
// @ts-nocheck
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { clone as _skeletonClone } from 'three/examples/jsm/utils/SkeletonUtils.js';

/* ============================================================
 * 角色骨骼重定向（给 Quaternius 休闲风角色用）
 * ------------------------------------------------------------
 * Quaternius 角色包（男性 62 根骨 / 女性 31 根骨）没有 sit / dance / sing，
 * 所以坐姿是「把动作剪辑按骨骼世界朝向增量搬到目标骨架」得来的：
 *   1. 源骨架（agent.glb 方块人 / base-rig-animated.glb 素模）按 30fps 采样；
 *   2. 每根骨头算「相对 rest 的世界旋转增量」，叠加到目标骨头 rest 上，
 *      再自顶向下还原成目标局部的四元数（这样两套骨架的本地轴朝向不同也没关系）；
 *   3. 骨盆高度固定到「身高 × hipFrac」（≈0.52m，正好落在办公椅上），
 *      前后位移跟随源；
 *   4. Quaternius 的 Foot.L/Foot.R 挂在 Root 上（IK 目标，动画直接写位置），
 *      不是小腿的子节点 —— 这类脚踝要按世界坐标驱动，否则腿弯了脚还钉在原地。
 * ============================================================ */
const GLTF_BONES = (root) => {
  const m = {};
  root.traverse((o) => { if (o.isBone) m[o.name] = o; });
  return m;
};
const gltfWorldQ = (o) => o.getWorldQuaternion(new THREE.Quaternion());
const gltfWorldP = (o) => o.getWorldPosition(new THREE.Vector3());

/** 源骨骼（agent.glb：three 加载后点号被去掉）→ 目标骨骼候选名（按优先级） */
const BONE_MAP_AGENT = {
  Hips: ['Hips'],
  Spine: ['Abdomen', 'Torso', 'Chest'],
  Chest: ['Chest', 'Torso'],
  Neck: ['Neck'],
  Head: ['Head'],
  UpperArmL: ['UpperArmL'], LowerArmL: ['LowerArmL'], HandL: ['WristL', 'PalmL', 'HandL'],
  UpperArmR: ['UpperArmR'], LowerArmR: ['LowerArmR'], HandR: ['WristR', 'PalmR', 'HandR'],
  UpperLegL: ['UpperLegL'], LowerLegL: ['LowerLegL'], FootL: ['FootL'],
  UpperLegR: ['UpperLegR'], LowerLegR: ['LowerLegR'], FootR: ['FootR']
};

/** 素模动作库（base-rig-animated.glb，DEF- 前缀）→ 目标骨骼候选名 */
const BONE_MAP_RIG = {
  'DEF-hips': ['Hips'],
  'DEF-spine001': ['Abdomen'], 'DEF-spine002': ['Torso'], 'DEF-spine003': ['Chest'],
  'DEF-neck': ['Neck'], 'DEF-head': ['Head'],
  'DEF-upper_armL': ['UpperArmL'], 'DEF-forearmL': ['LowerArmL'], 'DEF-handL': ['WristL', 'PalmL'],
  'DEF-upper_armR': ['UpperArmR'], 'DEF-forearmR': ['LowerArmR'], 'DEF-handR': ['WristR', 'PalmR'],
  'DEF-thighL': ['UpperLegL'], 'DEF-shinL': ['LowerLegL'], 'DEF-footL': ['FootL'],
  'DEF-thighR': ['UpperLegR'], 'DEF-shinR': ['LowerLegR'], 'DEF-footR': ['FootR']
};

/** 剪辑短名（去掉 `CharacterArmature|` 之类前缀） */
const clipShortName = (n) => String(n || '').split('|').pop().trim();

/** 按「等名 → 前缀 → 包含」三级模糊匹配找剪辑 */
function findClip(anims, cands) {
  const list = anims || [];
  for (const c of cands) {
    const k = String(c).toLowerCase();
    const hit = list.find((a) => clipShortName(a.name).toLowerCase() === k);
    if (hit) return hit;
  }
  for (const c of cands) {
    const k = String(c).toLowerCase();
    const hit = list.find((a) => clipShortName(a.name).toLowerCase().startsWith(k));
    if (hit) return hit;
  }
  for (const c of cands) {
    const k = String(c).toLowerCase();
    const hit = list.find((a) => clipShortName(a.name).toLowerCase().includes(k));
    if (hit) return hit;
  }
  return null;
}

/** 找 Hips / UpperLegL / UpperLegR 的最近公共祖先：只有它下移才能「连腿带身子」一起坐下去 */
function pelvisAnchorOf(bones) {
  const chainOf = (o) => { const a = []; let p = o; while (p && p.isBone) { a.push(p); p = p.parent; } return a; };
  const thighs = [bones.UpperLegL, bones.UpperLegR].filter(Boolean);
  if (!bones.Hips || !thighs.length) return bones.Hips || null;
  const sets = [bones.Hips, ...thighs].map((b) => new Set(chainOf(b)));
  for (const b of chainOf(bones.Hips)) {
    if (sets.every((s) => s.has(b))) return b;
  }
  return bones.Hips;
}

/**
 * 把源剪辑重定向到目标骨架。
 * @param {object} o
 * @param {object} o.srcProto  源 gltf { scene, animations }
 * @param {THREE.AnimationClip} o.clip 源动作
 * @param {object} o.dstProto  目标 gltf { scene }
 * @param {object} [o.srcMap]  源骨骼映射表（默认 BONE_MAP_AGENT）
 * @param {number} [o.hipFrac] 坐下后骨盆高度 / 身高（0.286 ≈ 1.82m 的人 0.52m）
 * @param {string} [o.name]    产物剪辑名
 */
function retargetClip({ srcProto, clip, dstProto, srcMap = BONE_MAP_AGENT, fps = 30, hipFrac = 0.286, name = 'sit' }) {
  const srcRest = _skeletonClone(srcProto.scene);
  srcRest.updateMatrixWorld(true);
  const srcBones = GLTF_BONES(srcRest);

  const dstRest = _skeletonClone(dstProto.scene);
  dstRest.updateMatrixWorld(true);
  const dstBones = GLTF_BONES(dstRest);
  const dstHeight = new THREE.Box3().setFromObject(dstRest).max.y || 1.8;
  const hipY = dstHeight * hipFrac;

  /* 骨骼映射 */
  const map = {};
  for (const [s, cands] of Object.entries(srcMap)) {
    if (!srcBones[s]) continue;
    const d = cands.find((n) => dstBones[n]);
    if (d) map[s] = d;
  }
  const invMap = {};
  for (const [s, d] of Object.entries(map)) invMap[d] = s;

  const srcRestQ = {}, srcRestPos = {};
  for (const s of Object.keys(map)) {
    srcRestQ[s] = gltfWorldQ(srcBones[s]);
    srcRestPos[s] = gltfWorldP(srcBones[s]);
  }

  const dstOrder = [];
  dstProto.scene.traverse((o) => { if (o.isBone) dstOrder.push(o.name); });
  const dstRestQ = {}, dstRestPos = {}, dstParent = {};
  for (const n of dstOrder) {
    const o = dstBones[n];
    dstRestQ[n] = gltfWorldQ(o);
    dstRestPos[n] = gltfWorldP(o);
    dstParent[n] = o.parent && o.parent.isBone ? o.parent.name : null;
  }

  const anchor = pelvisAnchorOf(dstBones);
  const anchorName = anchor ? anchor.name : null;
  const anchorParent = anchor ? anchor.parent : null;
  if (anchorParent) anchorParent.updateWorldMatrix(true, false);
  const srcPelvis = Object.keys(map).find((k) => map[k] === 'Hips') || 'Hips';

  /* 脚踝不在小腿下的（Quaternius 男性包）→ 按世界坐标驱动 */
  const footBones = ['FootL', 'FootR'].filter((n) => {
    const b = dstBones[n];
    if (!b) return false;
    const knee = dstBones[n === 'FootL' ? 'LowerLegL' : 'LowerLegR'];
    return !knee || b.parent !== knee;
  });

  /* 源动画采样 */
  const sampler = _skeletonClone(srcProto.scene);
  const smixer = new THREE.AnimationMixer(sampler);
  smixer.clipAction(clip).play();
  const samplerBones = GLTF_BONES(sampler);

  const nFrames = Math.max(2, Math.round((clip.duration || 1) * fps));
  const times = [];
  const quatSeries = new Map();
  const posSeries = new Map();
  const push3 = (n, v) => { if (!posSeries.has(n)) posSeries.set(n, []); posSeries.get(n).push(v.x, v.y, v.z); };
  const push4 = (n, q) => { if (!quatSeries.has(n)) quatSeries.set(n, []); quatSeries.get(n).push(q.x, q.y, q.z, q.w); };
  const pQ = new THREE.Quaternion(), pS = new THREE.Vector3(), pP = new THREE.Vector3();

  for (let f = 0; f <= nFrames; f++) {
    const t = (f / nFrames) * (clip.duration || 1);
    times.push(t);
    smixer.setTime(t);
    sampler.updateMatrixWorld(true);

    /* 源各骨骼相对 rest 的世界旋转增量 */
    const deltas = {};
    for (const s of Object.keys(map)) {
      deltas[map[s]] = gltfWorldQ(samplerBones[s]).multiply(srcRestQ[s].clone().invert());
    }

    /* 目标：自顶向下拼出世界朝向，再换成局部四元数 */
    const world = {};
    for (const n of dstOrder) {
      const rest = dstRestQ[n];
      if (!rest) continue;
      const pName = dstParent[n];
      const parentW = pName ? (world[pName] || dstRestQ[pName]) : new THREE.Quaternion();
      const want = deltas[n] ? deltas[n].clone().multiply(rest) : rest.clone();
      world[n] = want;
      if (deltas[n]) push4(n, parentW.clone().invert().multiply(want));
    }

    /* 骨盆：压到坐高（前后微移跟随源） */
    if (anchor) {
      const srcHipNow = gltfWorldP(samplerBones[srcPelvis]);
      const dWorld = new THREE.Vector3(
        srcHipNow.x - srcRestPos[srcPelvis].x,
        hipY - dstRestPos.Hips.y,
        srcHipNow.z - srcRestPos[srcPelvis].z
      );
      anchorParent.matrixWorld.decompose(pP, pQ, pS);
      const dLocal = dWorld.clone().applyQuaternion(pQ.clone().invert()).divide(pS);
      push3(anchorName, dstBones[anchorName].position.clone().add(dLocal));
    }

    /* 世界坐标驱动的脚踝：高度保持 rest（脚掌贴地），只跟前后的位移 */
    for (const n of footBones) {
      const s = invMap[n];
      const srcNow = gltfWorldP(samplerBones[s]);
      const want = new THREE.Vector3(
        dstRestPos[n].x + (srcNow.x - srcRestPos[s].x),
        dstRestPos[n].y,
        dstRestPos[n].z + (srcNow.z - srcRestPos[s].z)
      );
      const parent = dstBones[n].parent;
      parent.updateWorldMatrix(true, false);
      const local = want.clone().applyMatrix4(new THREE.Matrix4().copy(parent.matrixWorld).invert());
      push3(n, local);
    }
  }

  const tracks = [];
  for (const [n, arr] of quatSeries) tracks.push(new THREE.QuaternionKeyframeTrack(n + '.quaternion', times, arr));
  for (const [n, arr] of posSeries) tracks.push(new THREE.VectorKeyframeTrack(n + '.position', times, arr));
  return new THREE.AnimationClip(name, clip.duration || 1, tracks);
}

/* AI 办公室 · Three.js 场景 v3（人物骨架 + 屏幕发光 + 家具细节） */
export function createOffice(opts) {
  const stage = opts.stage;
  /* ---- 角色模型：Quaternius 休闲风角色（6 个外观，按名字 hash 分配；拿不到就继续用程序化小人） ---- */
  const CHAR_DIR = 'characters/quaternius/';
  const CHAR_FILES = [
    'casual_character.glb', 'hoodie_character.glb', 'business_man.glb',
    'beach_character.glb', 'worker.glb', 'woman_casual.glb'
  ];
  const CHAR_NAME_CN = {
    'casual_character.glb': '休闲男·灰T恤',
    'hoodie_character.glb': '休闲男·紫卫衣',
    'business_man.glb': '商务男·西装',
    'beach_character.glb': '休闲男·短裤',
    'worker.glb': '工装男·安全帽',
    'woman_casual.glb': '休闲女'
  };
  /* 女性包建模单位是男性包的 2.5 倍（4.6 → 1.84m），加载后要缩回来 */
  const CHAR_SCALE = { 'woman_casual.glb': 0.398 };
  /* 自绘角色（tools/blender/build_agent_v2.py 生成）：自带 idle/walk/sit/dance/sing 五条动作，
     不需要从别的骨架重定向，只按名字换衣服颜色 */
  const SELF_FILE = 'agent-v2.glb';
  const SELF_LOOKS = [
    { name: '蓝衬衫', fem: false, shirt: [0.56, 0.73, 0.92], pants: [0.54, 0.57, 0.64], skin: [0.96, 0.89, 0.84] },
    { name: '青绿衫', fem: true, shirt: [0.58, 0.84, 0.76], pants: [0.52, 0.55, 0.58], skin: [0.97, 0.90, 0.85] },
    { name: '紫罗兰', fem: true, shirt: [0.74, 0.68, 0.92], pants: [0.50, 0.51, 0.58], skin: [0.95, 0.87, 0.81] },
    { name: '珊瑚橙', fem: false, shirt: [0.94, 0.72, 0.62], pants: [0.56, 0.51, 0.47], skin: [0.96, 0.88, 0.83] },
    { name: '石板灰', fem: false, shirt: [0.68, 0.73, 0.80], pants: [0.48, 0.51, 0.57], skin: [0.97, 0.90, 0.86] },
    { name: '暖米色', fem: true, shirt: [0.84, 0.78, 0.66], pants: [0.46, 0.47, 0.52], skin: [0.95, 0.87, 0.81] }
  ];
  /* 发色：黑 / 深棕 / 棕 / 栗 / 红棕 / 灰（都是亚洲常见发色） */
  const HAIR_COLORS = [
    [0.24, 0.21, 0.20], [0.33, 0.25, 0.18], [0.42, 0.30, 0.20],
    [0.48, 0.29, 0.18], [0.50, 0.25, 0.20], [0.52, 0.52, 0.53]
  ];
  /* 表情贴图（make_face.py 生成）：说话时在 normal/talk 之间切，就是 v1 那套"有表情" */
  const FACE_MOODS = ['normal', 'talk', 'happy', 'think', 'busy', 'tired', 'blink'];
  let faceTex = null;
  function loadFaces(base) {
    if (faceTex) return;
    const ld = new THREE.TextureLoader();
    faceTex = {};
    FACE_MOODS.forEach((m) => {
      const t = ld.load(base + 'face_' + m + '.png');
      t.colorSpace = THREE.SRGBColorSpace;
      t.flipY = false;            // glTF 的 UV 原点在左上，必须和导出时一致
      t.anisotropy = 4;
      faceTex[m] = t;
    });
  }
  let selfProto = null;       // 自绘角色原型（自带 5 条动作）
  let charProtos = [];        // 加载成功的 [{ file, scene, animations, scale, sitClip, sitRoute }]
  let loadReport = [];        // 报告用：[{ file, ok }]
  let sitSources = null;      // { rig: {proto,clip,map}, agent: {proto,clip,map} }
  let danceSources = null;    // 蹦迪剪辑（素模 Dance_Loop）
  let singSources = null;     // 说话/主唱剪辑（素模 Talking_Loop）
  let useGltf = false;
  let gltfPromise = null;
  const W = () => stage.clientWidth || 940;
  const H = () => stage.clientHeight || 700;

  /* ================= 渲染 ================= */
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(W(), H());
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  /* 阴影贴图不必每帧重画：场景里几百个网格（5 人 × 78 个蒙皮网格）每帧重算 shadow pass
     很吃 CPU。改成手动刷新、每 4 帧一次，人物动作慢，肉眼看不出差别（实测 CPU 明显下降）。 */
  renderer.shadowMap.autoUpdate = false;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.setClearColor(0xf4f1ea, 1);
  stage.appendChild(renderer.domElement);

  const scene = new THREE.Scene();

  /* 环境反射：金属/玻璃没有 envMap 会发灰，用 RoomEnvironment 烘一张 */
  {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    scene.environmentIntensity = 0.12;
    pmrem.dispose();
  }

  const VIEW = 12.5;
  let aspect = W() / H();
  const camera = new THREE.OrthographicCamera(-VIEW * aspect / 2, VIEW * aspect / 2, VIEW / 2, -VIEW / 2, 0.1, 300);
  camera.position.set(14, 13.4, 14);
  camera.lookAt(0, 0.3, 0);
  /* 默认相机位（全景/恢复用；正对白板/大屏时相机要挪到墙前，结束后拉回这里） */
  const CAM_HOME = { x: 14, y: 13.4, z: 14 };

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0.42, 0.15, 0.12);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minPolarAngle = 0.8;
  controls.maxPolarAngle = 1.16;
  controls.minAzimuthAngle = Math.PI / 4 - 0.6;
  controls.maxAzimuthAngle = Math.PI / 4 + 0.6;
  controls.minZoom = 0.55;
  controls.maxZoom = 2.4;
  controls.update();

  /* ================= 灯光 ================= */
  /* 天光 */
  const hemi = new THREE.HemisphereLight(0xf2f7ff, 0xdfe3e8, 0.66);
  scene.add(hemi);

  /* 主光：从右前上方，阴影落到左后 */
  const sun = new THREE.DirectionalLight(0xfff9f0, 2.55);
  sun.position.set(7.5, 10.5, 6.5);
  sun.target.position.set(-0.6, 0, -0.6);
  scene.add(sun.target);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -10; sun.shadow.camera.right = 10;
  sun.shadow.camera.top = 10; sun.shadow.camera.bottom = -10;
  sun.shadow.camera.near = 2; sun.shadow.camera.far = 34;
  sun.shadow.bias = -0.00035;
  sun.shadow.normalBias = 0.015;
  sun.shadow.radius = 2.2;
  sun.shadow.camera.updateProjectionMatrix();
  scene.add(sun);

  /* 室内反射补光（不投影） */
  const bounce = new THREE.DirectionalLight(0xfff6e8, 0.95);
  bounce.position.set(2, 14, 6);
  scene.add(bounce);

  const fill = new THREE.DirectionalLight(0xe8f0fa, 0.42);
  fill.position.set(-9, 5, 6);
  scene.add(fill);

  /* 洗墙光：让两面背墙不发灰 */
  const wash = new THREE.DirectionalLight(0xfff8f0, 0.5);
  wash.position.set(-4, 3.2, 9);
  scene.add(wash);

  /* ================= 昼夜（23:00 之后只留加班那盏灯） ================= */
  const DAY_LIGHT = {
    hemi: 0.78, sun: 2.55, bounce: 1.2, fill: 0.42, wash: 0.5,
    sunColor: 0xfff9f0, bg: 0xf1f1f1, stage: '#f1f1f1'
  };
  const NIGHT_LIGHT = {
    /* 不能压太黑：家具轮廓要还能看出来，只有"人不在的工位"是暗的 */
    hemi: 0.34, sun: 0.22, bounce: 0.34, fill: 0.12, wash: 0.22,
    sunColor: 0xa8bcff, bg: 0x121821, stage: '#121821'
  };
  let night = false;

  function applyNight(on) {
    night = !!on;
    const p = night ? NIGHT_LIGHT : DAY_LIGHT;
    hemi.intensity = p.hemi;
    sun.intensity = p.sun;
    sun.color.set(p.sunColor);
    bounce.intensity = p.bounce;
    fill.intensity = p.fill;
    wash.intensity = p.wash;
    renderer.setClearColor(p.bg, 1);
    if (stage) stage.style.background = p.stage;
    applyScreens();
    refreshPlates();
    if (M.glassEdge) M.glassEdge.emissiveIntensity = night ? 1.5 : 0.18;
    if (typeof drawScreen === 'function') drawScreen();
    if (badgeData.open) drawBadge();
    if (opts && opts.onNight) opts.onNight(night);
  }

  /** 22:00 ~ 06:00 自动进夜间；null = 交还给时钟 */
  function setNight(v) {
    if (v === null || v === undefined) {
      const h = new Date().getHours();
      applyNight(h >= 22 || h < 6);
    } else {
      applyNight(v);
    }
  }

  /* ================= 材质 ================= */
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({
    color: c,
    roughness: o.r === undefined ? 0.9 : o.r,
    metalness: o.m === undefined ? 0 : o.m,
    transparent: !!o.opacity,
    opacity: o.opacity === undefined ? 1 : o.opacity,
    emissive: o.e === undefined ? 0x000000 : o.e,
    emissiveIntensity: o.ei === undefined ? 1 : o.ei
  });

  function noiseTexture(size, base, amount, repeat) {
    const cv = document.createElement('canvas');
    cv.width = cv.height = size;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, size, size);
    const img = ctx.getImageData(0, 0, size, size);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      const n = (Math.random() - 0.5) * amount;
      d[i] += n; d[i + 1] += n; d[i + 2] += n;
    }
    ctx.putImageData(img, 0, 0);
    const tex = new THREE.CanvasTexture(cv);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(repeat[0], repeat[1]);
    tex.anisotropy = 4;
    return tex;
  }

  /* ================= AI 生成的贴图（已做无缝化：镜像平铺） ================= */
  const TEXDATA = {
    floor: "data:image/jpeg;base64,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",
    wood: "data:image/jpeg;base64,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",
    fabric: "data:image/jpeg;base64,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"
  };
  const texLoader = new THREE.TextureLoader();
  function applyTex(mat, key, rx, ry, rot) {
    const t = texLoader.load(TEXDATA[key]);
    t.wrapS = t.wrapT = THREE.MirroredRepeatWrapping;
    t.repeat.set(rx, ry);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    if (rot) { t.rotation = rot; t.center.set(0.5, 0.5); }
    mat.map = t;
    mat.needsUpdate = true;
    return t;
  }
  const M = {
    floor: std('#e0e5ec', { r: 0.95 }),
    carpet: std('#d3dae4', { r: 1 }),
    rugEdge: std('#c6cdd9', { r: 1 }),
    lounge: std('#efe8dc', { r: 1 }),
    slab: std('#fcfdfe', { r: 0.85 }),
    wall: std('#fbf8f3', { r: 0.95 }),
    base: std('#ddd8cf'),
    desk: std('#fdfcf9', { r: 0.7 }),
    deskEdge: std('#e8edf5'),
    metal: std('#b3bfcd', { m: 0.22, r: 0.26 }),
    darkMetal: std('#8e9aa9', { m: 0.3, r: 0.3 }),
    chair: std('#e2e6ec', { r: 0.92 }),
    chairDark: std('#cbd2dc', { r: 0.9 }),
    screen: std('#42597a', { r: 0.3, e: 0x8fbfe8, ei: 0.55 }),
    screenSmall: std('#4b6183', { r: 0.3, e: 0x8fbfe8, ei: 0.4 }),
    glass: new THREE.MeshPhysicalMaterial({
      color: 0xd8e8f8, transparent: true, opacity: 0.16, roughness: 0.06,
      metalness: 0, side: THREE.DoubleSide, clearcoat: 1, clearcoatRoughness: 0.1
    }),
    accent: std('#cfe3f7'),
    plant: std('#9db39d', { r: 0.95 }),
    pot: std('#e6e2da'),
    paper: std('#ffffff', { r: 0.9 }),
    wood: std('#e9e3d8', { r: 0.72 }),
    woodDark: std('#ddd6c9', { r: 0.8 }),
    dark: std('#aab4c2', { r: 0.7 }),
    ceramic: std('#ffffff', { r: 0.35 }),
    frame: std('#e4eaf2', { m: 0.12, r: 0.42 }),
    frosted: new THREE.MeshStandardMaterial({ color: '#eef3f9', transparent: true, opacity: 0.72, roughness: 0.85, metalness: 0 }),
    cable: std('#9aa5b4', { r: 0.6 }),
    led: std('#fff6e6', { e: 0xffe9c4, ei: 0.9, r: 0.4 }),
    stickyA: std('#e8f2ff', { r: 0.9 }),
    stickyB: std('#fdf3e2', { r: 0.9 }),
    screenGlow: std('#cfe4fb', { e: 0xa8cdf3, ei: 0.75, r: 0.5 }),
    glassEdge: std('#cfe9ff', { e: 0x5ec8ff, ei: 0.2, r: 0.35 }),
    parasol: std('#f3f5f8', { r: 0.9 }),
    floor2: std('#eceff4', { r: 0.92 }),
    wall2: std('#f6f2ea', { r: 0.95 }),
    bulb: std('#fff3d6', { e: 0xffd9a0, ei: 0.8, r: 0.4 })
  };
  /* 金属 / 玻璃吃环境反射多一点（哑光面几乎不受影响，避免整屋发白） */
  ['metal', 'darkMetal', 'frame', 'glass', 'chrome'].forEach(k => {
    if (M[k] && M[k].isMeshStandardMaterial) M[k].envMapIntensity = 1.7;
  });
  applyTex(M.floor, 'floor', 7, 5);
  applyTex(M.carpet, 'fabric', 6, 4);
  applyTex(M.wood, 'wood', 2.2, 2.2);
  applyTex(M.chair, 'fabric', 2.4, 2.4);
  applyTex(M.chairDark, 'fabric', 2.4, 2.4);
  M.wall.map = noiseTexture(256, '#fbf8f3', 3, [8, 3]);


  /* ================= 显示器屏幕贴图（摸鱼 vs 干活） ================= */
  /* 屏幕是"活的"：同一种 kind 共用一张 canvas 纹理，主循环每 200ms（省电 500ms）
     重绘一次 —— 代码在滚、图表在跳、游戏画面在动、视频进度在走。
     只重绘「当前有人用」的 kind，7 张里通常只有 2~3 张在动，开销很小。 */
  const SCREEN_W = 256;
  const SCREEN_H = 160;
  const SCREEN_CV = {};
  const SCREEN_TEX = {};
  const SCREEN_IN_USE = new Set();

  /** 把某种屏幕画到 ctx 上（t = 秒，用于算动态相位）。可重复调用。 */
  function paintScreen(ctx, kind, t) {
    ctx.clearRect(0, 0, SCREEN_W, SCREEN_H);
    if (kind === 'work') {
      /* 干活：浅色编辑器（代码慢慢往上滚）+ 右侧柱状图跳动 + 光标闪 */
      ctx.fillStyle = '#f8fbfe'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#e9f0f8'; ctx.fillRect(0, 0, 256, 18);
      ctx.fillStyle = '#409eff'; ctx.fillRect(8, 5, 64, 8);
      const off = (t * 22) % 13;
      ctx.fillStyle = '#cfd8e3';
      for (let i = 0; i < 11; i++) {
        const y = 22 + i * 13 - off;
        if (y < 22 || y > 146) continue;
        ctx.fillRect(12, y, 120 - (i % 3) * 22, 5);
      }
      ctx.fillStyle = '#eaf2fb'; ctx.fillRect(148, 28, 96, 64);
      [14, 28, 20, 36, 30].forEach((h, i) => {
        const hh = h + Math.sin(t * 1.6 + i * 1.1) * 6;
        ctx.fillStyle = i === 3 ? '#409eff' : '#a9c8e8';
        ctx.fillRect(158 + i * 17, 88 - hh, 10, hh);
      });
      ctx.fillStyle = '#dbe7f5'; ctx.fillRect(0, 150, 256, 10);
      ctx.fillStyle = '#7fb3e8'; ctx.fillRect(148, 104, 96, 4);
      ctx.fillStyle = '#c9d6e4'; ctx.fillRect(148, 114, 70, 4);
      if (Math.floor(t * 2) % 2 === 0) {
        ctx.fillStyle = '#409eff'; ctx.fillRect(12, 24, 4, 9);
      }
    } else if (kind === 'game') {
      /* 摸鱼打游戏：小圆点左右走、血条掉、分数在涨 */
      ctx.fillStyle = '#1b2430'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#2b3849'; ctx.fillRect(0, 92, 256, 68);
      ctx.fillStyle = '#3b4c63'; ctx.fillRect(34, 58, 76, 44);
      ctx.fillStyle = '#33445a'; ctx.fillRect(150, 50, 60, 52);
      const px = 128 + Math.sin(t * 1.9) * 34;
      ctx.strokeStyle = '#7fd1ff'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(px, 82, 11, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(px, 66); ctx.lineTo(px, 98);
      ctx.moveTo(px - 16, 82); ctx.lineTo(px + 16, 82);
      ctx.stroke();
      ctx.fillStyle = '#e05c5c';
      ctx.fillRect(12, 10, 86 * (0.55 + Math.sin(t * 0.8) * 0.35), 8);
      ctx.fillStyle = '#5c8ae0'; ctx.fillRect(12, 24, 62, 6);
      ctx.fillStyle = '#243040'; ctx.fillRect(208, 8, 40, 40);
      ctx.fillStyle = '#5fd18b'; ctx.fillRect(222, 22, 8, 8);
      ctx.fillStyle = '#f0c040';
      ctx.fillRect(232 + Math.sin(t * 3) * 4, 34, 6, 6);
      ctx.fillStyle = '#d8dee8'; ctx.font = '9px sans-serif';
      ctx.fillText('ROUND 3  ' + String(1200 + (Math.floor(t * 7) % 900)), 100, 150);
    } else if (kind === 'sql') {
      /* 跑 SQL：深色编辑器 + 结果表格逐行出现 + 状态灯闪 */
      ctx.fillStyle = '#11161f'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#1b2431'; ctx.fillRect(0, 0, 256, 16);
      ctx.fillStyle = '#5fd18b'; ctx.fillRect(8, 5, 34, 6);
      ctx.fillStyle = '#7fd1ff'; ctx.fillRect(46, 5, 22, 6);
      const rows = ['#8b9bb4', '#c9d6e4', '#8b9bb4', '#7fb3e8', '#8b9bb4'];
      rows.forEach((c, i) => {
        ctx.fillStyle = c;
        ctx.fillRect(10, 26 + i * 12, 96 - (i % 3) * 18, 5);
      });
      ctx.fillStyle = '#1e2836'; ctx.fillRect(120, 24, 126, 78);
      ctx.fillStyle = '#2b3a4d'; ctx.fillRect(120, 24, 126, 12);
      const shown = 1 + Math.floor((t * 0.9) % 5);
      for (let r = 0; r < 5; r++) {
        for (let c = 0; c < 4; c++) {
          ctx.fillStyle = r <= shown
            ? (r === 0 ? '#33506e' : (r % 2 ? '#22303f' : '#1b2634'))
            : '#141c26';
          ctx.fillRect(124 + c * 30, 40 + r * 12, 27, 10);
        }
      }
      ctx.fillStyle = Math.floor(t * 2) % 2 ? '#5fd18b' : '#2f6b4a';
      ctx.fillRect(10, 96, 60, 5);
      ctx.fillStyle = '#3a4a5e'; ctx.fillRect(0, 150, 256, 10);
    } else if (kind === 'doc') {
      /* 写文档：白页 + 高亮段落在换 + 光标闪 */
      ctx.fillStyle = '#f6f4ef'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#ffffff'; ctx.fillRect(20, 14, 216, 132);
      ctx.fillStyle = '#e8e3d8'; ctx.fillRect(20, 14, 216, 3);
      ctx.fillStyle = '#c9c2b4';
      for (let i = 0; i < 7; i++) ctx.fillRect(32, 28 + i * 11, 190 - (i % 4) * 26, 4);
      const hl = Math.floor(t / 2.5) % 4;
      ctx.fillStyle = '#f2e4c8'; ctx.fillRect(28, 26 + hl * 11, 194, 16);
      ctx.fillStyle = '#b08948'; ctx.fillRect(32, 31 + hl * 11, 120, 5);
      ctx.fillStyle = '#d7d1c4'; ctx.fillRect(32, 100, 150, 4);
      ctx.fillStyle = '#b07d3f'; ctx.fillRect(32, 118, 34, 10);
      ctx.fillStyle = '#f8fbfe'; ctx.fillRect(200, 20, 26, 26);
      ctx.fillStyle = '#bcd8cd';
      ctx.fillRect(206, 26, 14, 3);
      ctx.fillRect(206, 32, 14, 3);
      if (Math.floor(t * 2.4) % 2 === 0) {
        ctx.fillStyle = '#7a6a52'; ctx.fillRect(190, 92, 2, 9);
      }
    } else if (kind === 'list') {
      /* 看报表：表格 + 柱子此起彼伏 */
      ctx.fillStyle = '#fbfcfe'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#eef3f9'; ctx.fillRect(0, 0, 256, 18);
      ctx.fillStyle = '#7fb3e8'; ctx.fillRect(10, 5, 46, 7);
      ctx.fillStyle = '#dbe7f5'; ctx.fillRect(64, 5, 30, 7);
      for (let r = 0; r < 6; r++) {
        ctx.fillStyle = r % 2 ? '#f4f8fc' : '#ffffff';
        ctx.fillRect(8, 24 + r * 16, 130, 14);
        ctx.fillStyle = '#c9d6e4';
        ctx.fillRect(14, 29 + r * 16, 44 - (r % 3) * 8, 4);
        ctx.fillRect(70, 29 + r * 16, 56 - (r % 4) * 10, 4);
      }
      const bars = [26, 44, 34, 58, 40];
      bars.forEach((h, i) => {
        const hh = h + Math.sin(t * 2.2 + i * 1.4) * 8;
        ctx.fillStyle = i === 3 ? '#409eff' : '#bcd8ef';
        ctx.fillRect(154 + i * 18, 132 - hh, 11, hh);
      });
      ctx.fillStyle = '#dbe7f5'; ctx.fillRect(0, 150, 256, 10);
    } else if (kind === 'video') {
      /* 看视频：画面在动 + 进度条往前走 + 字幕闪 */
      ctx.fillStyle = '#f4efe7'; ctx.fillRect(0, 0, 256, 160);
      ctx.fillStyle = '#d9cbb8'; ctx.fillRect(18, 18, 220, 104);
      ctx.fillStyle = '#e8dccb';
      ctx.fillRect(28 + Math.sin(t * 0.7) * 20, 30, 90, 60);
      ctx.fillStyle = '#cbb99f';
      ctx.beginPath();
      ctx.arc(170 + Math.cos(t * 0.9) * 16, 70 + Math.sin(t * 1.1) * 12, 18, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(255,255,255,0.45)';
      ctx.fillRect(18, 18, 220, 6);
      ctx.fillStyle = '#cfc2ae'; ctx.fillRect(18, 130, 220, 5);
      ctx.fillStyle = '#e05c5c';
      ctx.fillRect(18, 130, 220 * ((t * 0.02) % 1), 5);
      ctx.fillStyle = '#b9ab97'; ctx.fillRect(96, 128, 18, 8);
      if (Math.floor(t * 1.5) % 2 === 0) {
        ctx.fillStyle = '#8d7f6c'; ctx.fillRect(70, 112, 116, 5);
      }
    } else {
      ctx.fillStyle = '#1d232b'; ctx.fillRect(0, 0, 256, 160);
    }
  }

  ['work', 'game', 'video', 'sql', 'doc', 'list', 'off'].forEach((kind) => {
    const cv = document.createElement('canvas');
    cv.width = SCREEN_W;
    cv.height = SCREEN_H;
    SCREEN_CV[kind] = cv;
    paintScreen(cv.getContext('2d'), kind, 0);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    SCREEN_TEX[kind] = tex;
  });
  const DESK_SCREENS = [];   // 与 DESKS 顺序一致
  const DESK_GLOWS = [];     // 桌面光晕（按状态染色）

  /* ================= 小工具 ================= */
  /* 楼层：1F 在 y=0，2F 整体抬高 FLOOR_H；buildingFloor 决定新物体属于哪层 */
  const FLOOR_H = 3.55;
  let buildingFloor = 1;
  let buildingY = 0;

  function mesh(geo, material, x, y, z, opt = {}) {
    const m = new THREE.Mesh(geo, material);
    m.position.set(x || 0, (y || 0) + buildingY, z || 0);
    m.userData.floor = buildingFloor;
    if (opt.rx) m.rotation.x = opt.rx;
    if (opt.ry) m.rotation.y = opt.ry;
    if (opt.rz) m.rotation.z = opt.rz;
    m.castShadow = opt.cast !== false;
    m.receiveShadow = opt.receive !== false;
    (opt.parent || scene).add(m);
    return m;
  }
  const rbox = (w, h, d, r) => new RoundedBoxGeometry(w, h, d, 2, r === undefined ? 0.02 : r);
  const B = (w, h, d, material, x, y, z, r, opt) => mesh(rbox(w, h, d, r), material, x, y, z, opt);
  const C = (r1, r2, h, material, x, y, z, seg = 24, opt) => mesh(new THREE.CylinderGeometry(r1, r2, h, seg), material, x, y, z, opt);
  const S = (r, material, x, y, z, opt) => mesh(new THREE.SphereGeometry(r, 18, 14), material, x, y, z, opt);

  /* 绿植：陶盆 + 土 + 主干 + 6 片长叶（程序化，不占资源） */
  const PLANT_SOIL = std('#3b3128', { r: 0.95 });
  const PLANT_STEM = std('#5a4632', { r: 0.9 });
  function plant(x, z, scale, tone) {
    const g = new THREE.Group();
    g.position.set(x, buildingY, z);   // 关键：二层要落在二层楼板上
    g.scale.setScalar(scale || 1);
    g.userData.floor = buildingFloor;
    scene.add(g);
    /* 组已经带楼层高度了，组内子件不能再被 mesh() 加一次（否则花盆飘到半空） */
    const savedY = buildingY;
    buildingY = 0;
    const o = { parent: g, cast: false };
    C(0.2, 0.145, 0.28, M.ceramic, 0, 0.14, 0, 16, o);
    C(0.19, 0.19, 0.02, PLANT_SOIL, 0, 0.275, 0, 16, o);
    C(0.02, 0.026, 0.34, PLANT_STEM, 0, 0.44, 0, 6, o);
    const green = std(tone || '#5cb86b', { r: 0.88 });
    const dark = std(new THREE.Color(tone || '#5cb86b').multiplyScalar(0.82).getStyle(), { r: 0.88 });
    /* 叶子：扁椭圆（宽 0.1 / 长 0.4 / 厚 0.02），向外张开 */
    const leafGeo = new THREE.SphereGeometry(1, 10, 8);
    const leaves = [
      [0.0, 0.7, 0.02, 0.0, 0.18, 1.0],
      [0.17, 0.62, 0.06, 0.9, 0.35, 0.9],
      [-0.16, 0.6, 0.08, -0.95, 0.35, 0.9],
      [0.07, 0.56, -0.16, 0.3, -0.9, 0.85],
      [-0.06, 0.68, -0.13, -0.3, -0.85, 0.8],
      [0.12, 0.5, 0.14, 1.1, 0.75, 0.75],
      [-0.13, 0.48, 0.1, -1.15, 0.7, 0.7]
    ];
    leaves.forEach(([bx, by, bz, rz, rx, s2], i) => {
      const lf = new THREE.Mesh(leafGeo, i % 2 ? dark : green);
      lf.position.set(bx, by, bz);
      lf.scale.set(0.085 * s2, 0.23 * s2, 0.022);
      lf.rotation.set(rx * 0.8, i * 0.9, rz * 1.15);
      lf.castShadow = false;
      lf.userData.floor = buildingFloor;
      g.add(lf);
    });
    buildingY = savedY;
    return g;
  }

  /* ================= 房子 ================= */
  const FW = 13.5, FD = 9.5;
  B(FW + 0.44, 0.26, FD + 0.44, M.slab, 0, -0.13, 0, 0.03, { cast: false });
  B(FW, 0.08, FD, M.floor, 0, 0.0, 0, 0.02, { cast: false });
  const rug = (w, d, x, z, mat) => {
    B(w + 0.08, 0.008, d + 0.08, M.rugEdge, x, 0.044, z, 0.06, { cast: false });
    B(w, 0.012, d, mat, x, 0.05, z, 0.06, { cast: false });
  };
  rug(6.9, 3.6, -1.15, -1.15, M.carpet);
  rug(3.6, 2.4, -0.3, 3.45, M.lounge);
  rug(3.4, 2.0, 4.3, 2.0, M.carpet);

  /* 底座柔影 */
  {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 512;
    const ctx = cv.getContext('2d');
    const grd = ctx.createRadialGradient(256, 256, 40, 256, 256, 250);
    grd.addColorStop(0, 'rgba(30,40,55,0.24)');
    grd.addColorStop(0.55, 'rgba(30,40,55,0.10)');
    grd.addColorStop(1, 'rgba(30,40,55,0)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, 512, 512);
    const sh = new THREE.Mesh(
      new THREE.PlaneGeometry(21, 17),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(cv), transparent: true, depthWrite: false })
    );
    sh.rotation.x = -Math.PI / 2;
    sh.position.set(0, -0.32, 0);
    scene.add(sh);
  }

  /* 背墙（北墙带窗洞）+ 踢脚线 */
  const WZ = -FD / 2 - 0.08, WH = 1.78, WT = 0.16;
  const WIN = { x1: -2.0, x2: 2.0, y1: 0.84, y2: 1.62 };
  /* 窗两侧整段 */
  B(WIN.x1 - (-FW / 2 - 0.22), WH, WT, M.wall, (-FW / 2 - 0.22 + WIN.x1) / 2, WH / 2, WZ, 0.02);
  B((FW / 2 + 0.22) - WIN.x2, WH, WT, M.wall, (WIN.x2 + FW / 2 + 0.22) / 2, WH / 2, WZ, 0.02);
  /* 窗下墙 + 窗上墙 */
  B(WIN.x2 - WIN.x1, WIN.y1, WT, M.wall, 0, WIN.y1 / 2, WZ, 0.02);
  B(WIN.x2 - WIN.x1, WH - WIN.y2, WT, M.wall, 0, (WIN.y2 + WH) / 2, WZ, 0.02);
  /* 窗框 + 中挺 + 窗台 */
  B(WIN.x2 - WIN.x1 + 0.1, 0.06, 0.2, M.wall, 0, WIN.y2, WZ, 0.01);
  B(WIN.x2 - WIN.x1 + 0.1, 0.06, 0.2, M.wall, 0, WIN.y1, WZ, 0.01);
  B(0.06, WIN.y2 - WIN.y1, 0.2, M.wall, WIN.x1, (WIN.y1 + WIN.y2) / 2, WZ, 0.01);
  B(0.06, WIN.y2 - WIN.y1, 0.2, M.wall, WIN.x2, (WIN.y1 + WIN.y2) / 2, WZ, 0.01);
  [-0.66, 0.66].forEach(x => B(0.07, WIN.y2 - WIN.y1, 0.16, M.wall, x, (WIN.y1 + WIN.y2) / 2, WZ, 0.008));
  B(WIN.x2 - WIN.x1, 0.07, 0.16, M.wall, 0, (WIN.y1 + WIN.y2) / 2, WZ, 0.008);
  B(WIN.x2 - WIN.x1 + 0.34, 0.05, 0.3, M.desk, 0, WIN.y1 - 0.03, WZ + 0.12, 0.01);
  {
    const pane = new THREE.Mesh(
      new THREE.PlaneGeometry(WIN.x2 - WIN.x1, WIN.y2 - WIN.y1),
      new THREE.MeshBasicMaterial({ color: 0xe6f1fc })
    );
    pane.position.set(0, (WIN.y1 + WIN.y2) / 2, WZ + 0.02);
    scene.add(pane);
  }

  B(0.16, WH, FD + 0.44, M.wall, -FW / 2 - 0.08, WH / 2, 0, 0.02);
  B(FW + 0.3, 0.07, 0.02, M.base, 0, 0.08, -FD / 2 + 0.01, 0.005, { cast: false });
  B(0.02, 0.07, FD + 0.3, M.base, -FW / 2 + 0.01, 0.08, 0, 0.005, { cast: false });

  /* 墙上：时钟 + 白板（带便签） */
  C(0.2, 0.2, 0.03, M.paper, 3.2, 1.34, -FD / 2 + 0.01, 24, { rx: Math.PI / 2 });
  C(0.21, 0.21, 0.02, M.metal, 3.2, 1.34, -FD / 2 + 0.025, 24, { rx: Math.PI / 2 });
  B(0.015, 0.12, 0.005, M.dark, 3.2, 1.4, -FD / 2 + 0.035, 0.002);
  B(0.09, 0.015, 0.005, M.dark, 3.245, 1.34, -FD / 2 + 0.035, 0.002);

  B(1.6, 0.98, 0.04, M.paper, -5.5, 1.12, -FD / 2 + 0.03, 0.01, { cast: false });

  /* 白板贴图：把最近几条结论写上去（组长汇总完会走到板前说话） */
  const BOARD_DS = 2;
  const BOARD_LW = 512, BOARD_LH = 320;
  const BOARD_CV = document.createElement('canvas');
  BOARD_CV.width = BOARD_LW * BOARD_DS;
  BOARD_CV.height = BOARD_LH * BOARD_DS;
  const BOARD_CTX = BOARD_CV.getContext('2d');
  const BOARD_TEX = new THREE.CanvasTexture(BOARD_CV);
  BOARD_TEX.colorSpace = THREE.SRGBColorSpace;
  BOARD_TEX.anisotropy = 8;

  function wrapBoard(ctx, text, x, y, maxW, lh, maxLines) {
    let line = '';
    let n = 0;
    for (const ch of text) {
      if (n >= maxLines) return y;
      if (ctx.measureText(line + ch).width > maxW) {
        ctx.fillText(line, x, y);
        y += lh;
        n++;
        line = ch;
      } else {
        line += ch;
      }
    }
    if (line && n < maxLines) {
      ctx.fillText(line, x, y);
      y += lh;
    }
    return y;
  }

  let lastBoardLines = [];
  function drawBoard(lines) {
    lastBoardLines = (lines || []).slice(0, 5);
    const ctx = BOARD_CTX;
    ctx.setTransform(BOARD_DS, 0, 0, BOARD_DS, 0, 0);
    ctx.fillStyle = '#f8f5ee';
    ctx.fillRect(0, 0, BOARD_LW, BOARD_LH);
    ctx.fillStyle = '#2e2a24';
    ctx.font = 'bold 26px "Microsoft YaHei", sans-serif';
    ctx.fillText('最近结论', 28, 46);
    ctx.fillStyle = '#b07d3f';
    ctx.fillRect(28, 58, 54, 3);
    ctx.font = '19px "Microsoft YaHei", sans-serif';
    let y = 92;
    const list = (lines || []).slice(0, 5);
    if (!list.length) {
      ctx.fillStyle = '#b3aaa0';
      ctx.fillText('还没有派活记录', 28, y);
    }
    list.forEach((t, i) => {
      ctx.fillStyle = '#c9b189';
      ctx.fillText(`${i + 1}.`, 28, y);
      ctx.fillStyle = '#3c372f';
      y = wrapBoard(ctx, String(t || '').replace(/\s+/g, ' '), 52, y, 430, 24, 2) + 8;
    });
    BOARD_TEX.needsUpdate = true;
  }
  /** 白板第二种版式：当前任务 + 分工（派活时用，结论时再切回 drawBoard） */
  function drawTaskBoard(task, rows) {
    const ctx = BOARD_CTX;
    ctx.setTransform(BOARD_DS, 0, 0, BOARD_DS, 0, 0);
    ctx.fillStyle = '#f8f5ee';
    ctx.fillRect(0, 0, BOARD_LW, BOARD_LH);
    ctx.fillStyle = '#2e2a24';
    ctx.font = 'bold 26px "Microsoft YaHei", sans-serif';
    ctx.fillText('当前任务', 28, 46);
    ctx.fillStyle = '#b07d3f';
    ctx.fillRect(28, 58, 54, 3);

    ctx.fillStyle = '#3c372f';
    ctx.font = '19px "Microsoft YaHei", sans-serif';
    const body = String(task || '').replace(/\s+/g, ' ').slice(0, 60);
    let y = wrapBoard(ctx, body, 28, 92, 456, 24, 2) + 10;

    ctx.strokeStyle = '#ddd3c4';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(28, y + 6);
    ctx.lineTo(484, y + 6);
    ctx.stroke();

    ctx.fillStyle = '#8a7f70';
    ctx.font = 'bold 17px "Microsoft YaHei", sans-serif';
    ctx.fillText('分工', 28, y + 34);

    ctx.font = '17px "Microsoft YaHei", sans-serif';
    (rows || []).slice(0, 3).forEach((r, i) => {
      const yy = y + 62 + i * 26;
      const done = !!r.done;
      ctx.fillStyle = done ? '#3f9d6a' : '#b07d3f';
      ctx.fillText(done ? '✓' : '·', 28, yy);
      ctx.fillStyle = done ? '#3f9d6a' : '#3c372f';
      ctx.fillText(String(r.who || '').slice(0, 10), 44, yy);
      ctx.fillStyle = done ? '#7fae95' : '#6f665a';
      ctx.fillText(String(r.task || '').replace(/\s+/g, ' ').slice(0, 22), 150, yy);
    });
    if (!(rows || []).length) {
      ctx.fillStyle = '#b3aaa0';
      ctx.fillText('组长正在安排…', 44, y + 62);
    }
    BOARD_TEX.needsUpdate = true;
  }

  /** 开工动员：全员先到白板前站一下（4.5 秒后各自回座，随后派活会把人带去工位） */
  function kickoff(names, ms = 4500) {
    const spots = [
      [-5.30, -3.02], [-4.78, -2.86], [-4.28, -2.80], [-3.92, -3.06], [-4.60, -3.34]
    ];
    const leader = agents.find(r => r.data && r.data.isLeader);
    if (leader) {
      walkTo(leader, -5.02, -3.62, Math.PI, 'stand', () => {
        lookAtPoint(leader, -5.5, -4.2, Math.ceil(ms / 1000));
      });
    }
    const movers = [];
    (names || []).forEach((nm, i) => {
      const r = agents.find(x => x.data && x.data.name === nm);
      if (!r) return;
      const sp = spots[i % spots.length];
      movers.push(r);
      walkTo(r, sp[0], sp[1], Math.PI, 'stand', () => {
        lookAtPoint(r, -5.5, -4.2, Math.ceil(ms / 1000));
        r.meetUntil = nowT + ms / 1000;      // 开会：点头 + 频繁看旁边
      });
    });
    if (!movers.length) return;
    window.setTimeout(() => {
      movers.forEach((r) => {
        if (r.seat) moveTo(r, r.seat);
      });
    }, ms);
  }

  drawBoard([]);

  const boardMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1.5, 0.88),
    new THREE.MeshBasicMaterial({ map: BOARD_TEX, toneMapped: false })
  );
  boardMesh.position.set(-5.5, 1.12, -FD / 2 + 0.056);
  boardMesh.userData.floor = 1;
  scene.add(boardMesh);
  B(1.62, 0.05, 0.05, M.metal, -5.5, 1.63, -FD / 2 + 0.04, 0.01, { cast: false });
  for (let i = 0; i < 4; i++) {
    B(0.82 - i * 0.14, 0.016, 0.006, M.dark, -5.75 + (i % 2) * 0.18, 1.42 - i * 0.16, -FD / 2 + 0.052, 0.002, { cast: false });
  }
  [[-5.32, 1.42, M.stickyA], [-5.18, 1.2, M.stickyB], [-5.45, 0.98, M.stickyA]].forEach(([x, y, m]) => {
    B(0.14, 0.14, 0.005, m, x, y, -FD / 2 + 0.055, 0.003, { cast: false, ry: 0.12 });
  });

  /* ================= 工位 ================= */
  const DESKS = [
    { x: -2.0, z: -2.4 }, { x: 0.7, z: -1.8 },
    { x: -3.1, z: -0.6 }, { x: -0.4, z: 0.0 }
  ];

  function chair(x, z, ry, dark) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    g.rotation.y = ry || 0;
    scene.add(g);
    const o = { parent: g };
    const fab = dark ? M.chairDark : M.chair;
    /* 坐垫（厚一点）+ 靠背（微后仰）+ 腰托 */
    B(0.48, 0.1, 0.46, fab, 0, 0.47, 0, 0.05, o);
    B(0.46, 0.42, 0.08, fab, 0, 0.7, 0.22, 0.04, { ...o, rx: 0.12 });
    B(0.34, 0.12, 0.05, fab, 0, 0.55, 0.235, 0.02, { ...o, rx: 0.12 });
    /* 扶手：托面 + 立杆 */
    [-1, 1].forEach(sd => {
      B(0.06, 0.05, 0.32, M.darkMetal, sd * 0.24, 0.66, 0.02, 0.02, o);
      B(0.045, 0.16, 0.045, M.metal, sd * 0.24, 0.57, 0.14, 0.012, o);
    });
    /* 气杆 + 五星脚 + 滚轮 */
    C(0.036, 0.042, 0.36, M.metal, 0, 0.24, 0, 12, o);
    C(0.1, 0.12, 0.05, M.darkMetal, 0, 0.08, 0, 14, o);
    for (let i = 0; i < 5; i++) {
      const a = i / 5 * Math.PI * 2;
      B(0.3, 0.028, 0.06, M.darkMetal, Math.cos(a) * 0.14, 0.055, Math.sin(a) * 0.14, 0.01,
        { ...o, ry: -a });
      S(0.028, M.metal, Math.cos(a) * 0.29, 0.028, Math.sin(a) * 0.29, { ...o, cast: false });
    }
    return g;
  }

  /* 吧台凳：单柱 + 圆盘底座 + 脚踏圈 + 坐垫（像真的高脚吧凳） */
  function stool(x, z, seatY, ry) {
    const g = new THREE.Group();
    g.position.set(x, buildingY, z);
    g.rotation.y = ry || 0;
    g.userData.floor = buildingFloor;
    scene.add(g);
    const savedY = buildingY;
    buildingY = 0;
    const o = { parent: g, cast: false };
    const sy = seatY || 0.64;

    /* 底座：略外扩的圆盘 + 一圈亮边 */
    C(0.2, 0.225, 0.035, M.darkMetal, 0, 0.018, 0, 24, o);
    C(0.205, 0.215, 0.012, M.metal, 0, 0.041, 0, 24, o);

    /* 气杆：上细下粗 */
    const colH = sy - 0.11;
    C(0.033, 0.052, colH, M.metal, 0, 0.05 + colH / 2, 0, 16, o);

    /* 脚踏圈 */
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.012, 6, 24), M.metal);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = sy * 0.42;
    ring.castShadow = false;
    ring.userData.floor = buildingFloor;
    g.add(ring);

    /* 坐垫：深色托板 + 圆垫 */
    C(0.175, 0.175, 0.018, M.darkMetal, 0, sy - 0.055, 0, 22, o);
    C(0.19, 0.178, 0.055, M.chair, 0, sy - 0.025, 0, 24, o);

    buildingY = savedY;
    return g;
  }

  function cable(x1, y1, z1, x2, y2, z2, sag) {
    const p0 = new THREE.Vector3(x1, y1, z1), p1 = new THREE.Vector3(x2, y2, z2);
    const mid = p0.clone().add(p1).multiplyScalar(0.5);
    mid.y -= sag === undefined ? 0.06 : sag;
    const curve = new THREE.QuadraticBezierCurve3(p0, mid, p1);
    const geo = new THREE.TubeGeometry(curve, 12, 0.008, 5, false);
    const m = new THREE.Mesh(geo, M.cable);
    m.castShadow = true;
    scene.add(m);
    return m;
  }

  function desk(d) {
    const { x, z } = d;
    B(1.52, 0.05, 0.76, M.desk, x, 0.74, z, 0.02);
    B(1.44, 0.02, 0.68, M.deskEdge, x, 0.712, z, 0.01, { cast: false });
    /* 抽屉柜占着右下角（x+0.5, z+0.1），那根桌腿省掉，否则会穿进柜子里 */
    [[-0.68, -0.3], [0.68, -0.3], [-0.68, 0.3]].forEach(([dx, dz]) => {
      B(0.05, 0.72, 0.05, M.metal, x + dx, 0.36, z + dz, 0.012);
    });
    B(1.3, 0.03, 0.03, M.metal, x, 0.18, z - 0.3, 0.01, { cast: false });

    /* 抽屉柜 */
    B(0.42, 0.56, 0.52, M.desk, x + 0.5, 0.32, z + 0.1, 0.02);
    [0.46, 0.28, 0.1].forEach((y, i) => {
      B(0.38, 0.15, 0.02, M.deskEdge, x + 0.5, y, z + 0.37, 0.008, { cast: false });
      B(0.14, 0.018, 0.02, M.metal, x + 0.5, y + 0.02, z + 0.385, 0.008, { cast: false });
    });

    /* 显示器：底座/支架 + 一个整体 group（边框和屏幕在同一坐标系里，绝不脱开） */
    const mx = x + 0.3;   // 显示器靠右摆，避开人的身体遮挡
    B(0.24, 0.018, 0.17, M.metal, mx, 0.775, z - 0.14, 0.008);
    B(0.05, 0.26, 0.05, M.darkMetal, mx, 0.9, z - 0.16, 0.012);
    const mon = new THREE.Group();
    mon.userData.floor = buildingFloor;
    /* group 自己带楼层高度；子件用 new Mesh 直接建，不走 mesh()，避免再叠一次 buildingY */
    mon.position.set(mx, 1.05 + buildingY, z - 0.17);
    mon.rotation.x = -0.26;
    scene.add(mon);
    const bezel = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.3, 0.024), M.darkMetal);
    bezel.castShadow = false;
    bezel.userData.floor = buildingFloor;
    mon.add(bezel);
    const scrMat = new THREE.MeshBasicMaterial({ map: SCREEN_TEX.work });
    const scrPane = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.25, 0.006), scrMat);
    scrPane.position.set(0, 0.006, 0.0135);
    scrPane.userData.floor = buildingFloor;
    mon.add(scrPane);
    DESK_SCREENS.push(scrMat);
    /* 屏幕外溢的光 */
    {
      const glow = new THREE.Mesh(
        new THREE.PlaneGeometry(0.72, 0.5),
        new THREE.MeshBasicMaterial({
          map: (() => {
            const cv = document.createElement('canvas');
            cv.width = cv.height = 128;
            const ctx = cv.getContext('2d');
            const g = ctx.createRadialGradient(64, 64, 2, 64, 64, 62);
            g.addColorStop(0, 'rgba(140,190,240,0.55)');
            g.addColorStop(1, 'rgba(140,190,240,0)');
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, 128, 128);
            return new THREE.CanvasTexture(cv);
          })(),
          transparent: true, depthWrite: false, opacity: 0.34
        })
      );
      glow.userData.floor = buildingFloor;
      /* 贴在桌面上的柔光（原来悬在 1.03 高度，看起来像一块蓝板） */
      glow.position.set(mx, 0.752 + buildingY, z - 0.05);
      glow.rotation.x = -Math.PI / 2;
      scene.add(glow);
      DESK_GLOWS.push(glow.material);
    }

    /* 键鼠 + 杯子 + 纸 */
    B(0.34, 0.014, 0.12, M.desk, x - 0.22, 0.77, z + 0.12, 0.006);
    B(0.06, 0.022, 0.09, M.desk, x + 0.1, 0.772, z + 0.14, 0.01);
    C(0.042, 0.038, 0.085, M.ceramic, x - 0.55, 0.8, z + 0.16, 16);
    B(0.2, 0.01, 0.26, M.paper, x + 0.42, 0.772, z - 0.02, 0.004, { ry: 0.2 });

    /* 台灯 */
    C(0.07, 0.08, 0.02, M.metal, x - 0.6, 0.775, z - 0.22, 16);
    C(0.014, 0.014, 0.3, M.metal, x - 0.6, 0.93, z - 0.22, 10);
    const shade = mesh(new THREE.ConeGeometry(0.09, 0.1, 16, 1, true), M.desk, x - 0.55, 1.07, z - 0.18, { rz: -0.5 });
    shade.castShadow = true;

    /* 桌角小盆栽：小盆 + 三片叶子（不是一颗绿球） */
    C(0.05, 0.042, 0.07, M.pot, x - 0.62, 0.775, z + 0.3, 12);
    [[0, 0.085, 0], [-0.028, 0.07, 0.018], [0.028, 0.066, -0.018]].forEach(([dx, dy, dz], i) => {
      const lf = mesh(new THREE.SphereGeometry(1, 8, 6), M.plant,
        x - 0.62 + dx, 0.79 + dy, z + 0.3 + dz, { cast: false });
      lf.scale.set(0.042, 0.072, 0.028);
      lf.rotation.z = (i - 1) * 0.55;
      lf.rotation.x = dz * 8;
    });
    /* 便签 */
    B(0.07, 0.004, 0.07, M.stickyB, x + 0.16, 0.772, z + 0.3, 0.002, { cast: false, ry: 0.2 });

    /* 线缆 */
    cable(x + 0.02, 0.78, z - 0.14, x - 0.3, 0.72, z - 0.34, 0.05);

    chair(x, z + 0.63, 0);
  }
  DESKS.forEach(desk);


  /* ================= 前台 ================= */
  B(2.42, 0.94, 0.68, M.desk, -3.9, 0.47, 2.7, 0.03);
  B(2.52, 0.05, 0.74, M.desk, -3.9, 0.965, 2.7, 0.02);
  B(2.1, 0.4, 0.02, M.deskEdge, -3.9, 0.62, 3.042, 0.01, { cast: false });
  B(1.1, 0.05, 0.012, M.accent, -3.9, 0.86, 3.058, 0.006, { cast: false });
  /* 台面下沿一圈冷光：夜里把"入口"也点亮，和玻璃房同一支青 */
  B(2.3, 0.018, 0.02, M.glassEdge, -3.9, 0.10, 3.045, 0.006, { cast: false });
  B(2.3, 0.02, 0.02, M.glassEdge, -3.9, 0.905, 3.05, 0.006, { cast: false });
  B(0.12, 0.12, 0.012, M.accent, -4.6, 0.62, 3.058, 0.02, { cast: false });
  B(0.34, 0.03, 0.24, M.paper, -4.35, 0.99, 2.6, 0.008, { ry: 0.18 });
  B(0.28, 0.02, 0.2, M.paper, -4.4, 1.0, 2.64, 0.006, { ry: 0.1 });
  C(0.042, 0.038, 0.085, M.ceramic, -3.3, 1.03, 2.55, 16);
  B(0.26, 0.16, 0.02, M.screenSmall, -3.55, 1.1, 2.5, 0.008, { rx: -0.14, cast: false });
  chair(-3.95, 2.05, Math.PI, true);

  /* ================= 玻璃房 ================= */
  const GX = 4.8, GZ = -3.1, GS = 2.9, GH = 2.05;
  const GLASS_LOW = 0.92;   // 下部磨砂实心带高度（真实会议室都这么做）
  function glassRun(w, x, z, ry) {
    const g = new THREE.Group();
    g.position.set(x, 0, z);
    if (ry) g.rotation.y = ry;
    scene.add(g);
    const o = { parent: g };
    const H = GH;

    B(w, GLASS_LOW, 0.05, M.frosted, 0, GLASS_LOW / 2, 0, 0.01, { ...o, cast: false, receive: false });
    const pane = new THREE.Mesh(new THREE.BoxGeometry(w, H - GLASS_LOW - 0.06, 0.02), M.glass);
    pane.position.set(0, GLASS_LOW + (H - GLASS_LOW - 0.06) / 2, 0);
    pane.castShadow = false;
    pane.receiveShadow = false;
    pane.userData.floor = buildingFloor;
    g.add(pane);
    B(w, 0.05, 0.07, M.frame, 0, GLASS_LOW, 0, 0.01, o);
    B(w, 0.05, 0.07, M.frame, 0, H - 0.025, 0, 0.01, o);
    /* 夜间轮廓光：顶沿 + 地脚（白天很淡，夜里勾出会客室） */
    B(w, 0.012, 0.085, M.glassEdge, 0, H - 0.004, 0, 0.004, { ...o, cast: false, receive: false });
    B(w, 0.01, 0.05, M.glassEdge, 0, 0.018, 0, 0.003, { ...o, cast: false, receive: false });
    B(0.05, H, 0.07, M.frame, -w / 2 + 0.025, H / 2, 0, 0.01, o);
    B(0.05, H, 0.07, M.frame, w / 2 - 0.025, H / 2, 0, 0.01, o);
    const n = Math.max(1, Math.round(w / 0.7) - 1);
    for (let i = 1; i <= n; i++) {
      B(0.035, H - GLASS_LOW - 0.06, 0.05, M.frame,
        -w / 2 + (w / (n + 1)) * i, GLASS_LOW + (H - GLASS_LOW - 0.06) / 2, 0, 0.008, o);
    }
    return g;
  }
  glassRun(GS, GX, GZ - GS / 2, 0);
  glassRun(GS, GX, GZ + GS / 2, 0);
  glassRun(GS, GX - GS / 2, GZ, Math.PI / 2);
  glassRun(GS, GX + GS / 2, GZ, Math.PI / 2);

  /* 门：与墙面齐平、微开、带把手 */
  const door = new THREE.Group();
  door.position.set(GX + 0.5, 0, GZ + GS / 2);
  door.rotation.y = -0.22;
  scene.add(door);
  {
    const o = { parent: door };
    B(0.9, GLASS_LOW, 0.05, M.frosted, 0, GLASS_LOW / 2, 0, 0.01, { ...o, cast: false, receive: false });
    const pane = new THREE.Mesh(new THREE.BoxGeometry(0.9, GH - GLASS_LOW - 0.06, 0.02), M.glass);
    pane.position.set(0, GLASS_LOW + (GH - GLASS_LOW - 0.06) / 2, 0);
    pane.castShadow = false;
    pane.receiveShadow = false;
    pane.userData.floor = buildingFloor;
    door.add(pane);
    B(0.9, 0.05, 0.07, M.frame, 0, GLASS_LOW, 0, 0.01, o);
    B(0.9, 0.05, 0.07, M.frame, 0, GH - 0.025, 0, 0.01, o);
    B(0.05, GH, 0.07, M.frame, -0.43, GH / 2, 0, 0.01, o);
    B(0.05, GH, 0.07, M.frame, 0.43, GH / 2, 0, 0.01, o);
    B(0.03, 0.26, 0.03, M.metal, 0.33, 1.02, 0.05, 0.012, o);
  }

  /* 会议桌：1.5 × 0.85，两端各一把椅子 */
  B(1.5, 0.05, 0.85, M.desk, GX, 0.74, GZ, 0.03);
  B(1.38, 0.02, 0.73, M.deskEdge, GX, 0.712, GZ, 0.02, { cast: false });
  [[-0.64, -0.34], [0.64, -0.34], [-0.64, 0.34], [0.64, 0.34]].forEach(([dx, dz]) => {
    B(0.05, 0.72, 0.05, M.metal, GX + dx, 0.36, GZ + dz, 0.012);
  });
  /* 桌面：两份文件 + 一台笔记本 + 一杯水 */
  B(0.3, 0.02, 0.22, M.paper, GX - 0.34, 0.775, GZ + 0.02, 0.005, { ry: 0.12 });
  B(0.3, 0.02, 0.22, M.paper, GX - 0.32, 0.795, GZ + 0.05, 0.005, { ry: -0.08 });
  B(0.34, 0.02, 0.24, M.laptop, GX + 0.26, 0.78, GZ, 0.01);
  B(0.34, 0.22, 0.02, M.screen, GX + 0.26, 0.89, GZ - 0.12, 0.008, { rx: -0.28, cast: false });
  C(0.038, 0.034, 0.08, M.ceramic, GX + 0.02, 0.795, GZ + 0.26, 14);
  /* 椅子：南侧（工位）与北侧各一把 */
  chair(GX, GZ + 0.72, 0);
  chair(GX, GZ - 0.72, Math.PI);

  /* 门牌（可改写：接待访客时换成对方名字） */
  const SIGN_DS = 2;
  const SIGN_LW = 512, SIGN_LH = 128;
  const signCv = document.createElement('canvas');
  signCv.width = SIGN_LW * SIGN_DS; signCv.height = SIGN_LH * SIGN_DS;
  const signCtx = signCv.getContext('2d');
  const signTex = new THREE.CanvasTexture(signCv);
  signTex.colorSpace = THREE.SRGBColorSpace;
  signTex.anisotropy = 8;

  function setRoomSign(title, sub) {
    signCtx.setTransform(SIGN_DS, 0, 0, SIGN_DS, 0, 0);
    signCtx.fillStyle = '#ffffff';
    signCtx.fillRect(0, 0, SIGN_LW, SIGN_LH);
    signCtx.fillStyle = '#2b3a4d';
    signCtx.font = 'bold 50px "Microsoft YaHei", sans-serif';
    signCtx.textAlign = 'center';
    signCtx.textBaseline = 'middle';
    signCtx.fillText(String(title || '').slice(0, 8), 256, 52);
    signCtx.fillStyle = '#8fa2b8';
    signCtx.font = '26px "Microsoft YaHei", sans-serif';
    signCtx.fillText(String(sub || '').slice(0, 18), 256, 98);
    signTex.needsUpdate = true;
  }
  setRoomSign('质检室', 'QUALITY CHECK');

  {
    const sign = new THREE.Mesh(
      new THREE.PlaneGeometry(0.62, 0.155),
      new THREE.MeshBasicMaterial({ map: signTex })
    );
    sign.position.set(GX + 0.5, 1.86, GZ + GS / 2 + 0.05);
    scene.add(sign);
    B(0.66, 0.19, 0.03, M.frame, GX + 0.5, 1.86, GZ + GS / 2 + 0.035, 0.01, { cast: false });
  }

  /* ================= 办公室大屏（简报 / 结论，直接渲成 3D 贴图） ================= */
  const SCR_W = 2.4, SCR_H = 1.35;
  /* 屏幕贴图：物理分辨率按 DPR 放大，绘制时用逻辑宽高（布局坐标不变），文字更清晰 */
  const SCR_DS = 2;
  const SCR_LW = 1024, SCR_LH = 576;
  const scrCv = document.createElement('canvas');
  scrCv.width = SCR_LW * SCR_DS;
  scrCv.height = SCR_LH * SCR_DS;
  const scrCtx = scrCv.getContext('2d');
  const scrTex = new THREE.CanvasTexture(scrCv);
  scrTex.colorSpace = THREE.SRGBColorSpace;
  scrTex.anisotropy = 8;

  const scrGroup = new THREE.Group();
  scrGroup.position.set(-3.4, 0.98, -FD / 2 + 0.1);
  scene.add(scrGroup);

  /* 边框 + 屏幕 + 顶部一盏冷光（夜里亮） */
  B(SCR_W + 0.11, SCR_H + 0.11, 0.07, M.darkMetal || M.frame, 0, 0, -0.04, 0.02, { parent: scrGroup, cast: false });
  const scrMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(SCR_W, SCR_H),
    new THREE.MeshBasicMaterial({ map: scrTex })
  );
  scrMesh.position.z = 0.005;
  scrGroup.add(scrMesh);
  const scrGlow = new THREE.PointLight(0x9fd0ff, 0, 4.5);
  scrGlow.position.set(0, 0.2, 0.7);
  scrGroup.add(scrGlow);

  const scrState = { mode: 'idle', data: null };

  /** 屏幕配色：白天像纸，夜里像终端（跟场景昼夜一致） */
  function scrPalette() {
    return night
      ? { bg: '#0d1522', bg2: '#111c2c', fg: '#dbe7f5', mut: '#7f93a8', acc: '#5ec8ff', line: 'rgba(122,190,255,.22)' }
      : { bg: '#f6f8fb', bg2: '#eef3f9', fg: '#1f2b3a', mut: '#6b7d92', acc: '#2f7fd6', line: 'rgba(47,127,214,.18)' };
  }

  function wrapText(ctx, text, x, y, maxW, lh, maxLines) {
    const chars = String(text || '').split('');
    let line = '';
    let lines = 0;
    for (let i = 0; i < chars.length; i++) {
      const test = line + chars[i];
      if (ctx.measureText(test).width > maxW && line) {
        ctx.fillText(line, x, y);
        y += lh;
        lines++;
        line = chars[i];
        if (lines >= maxLines - 1) {
          // 最后一行：把剩下的塞进去并截断
          let rest = chars.slice(i).join('');
          while (rest && ctx.measureText(rest + '…').width > maxW) rest = rest.slice(0, -1);
          ctx.fillText(rest + (rest.length < chars.length - i ? '…' : ''), x, y);
          return y + lh;
        }
      } else {
        line = test;
      }
    }
    if (line) {
      ctx.fillText(line, x, y);
      y += lh;
    }
    return y;
  }

  function drawScreen() {
    const p = scrPalette();
    /* 物理画布是 SCR_DS 倍，绘制时统一放大到物理像素，布局坐标仍按逻辑宽高 */
    scrCtx.setTransform(SCR_DS, 0, 0, SCR_DS, 0, 0);
    const W = SCR_LW, H = SCR_LH;
    const g = scrCtx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, p.bg);
    g.addColorStop(1, p.bg2);
    scrCtx.fillStyle = g;
    scrCtx.fillRect(0, 0, W, H);

    /* 顶部细线 + 角标（跟场景里其它 UI 一个语言） */
    scrCtx.strokeStyle = p.line;
    scrCtx.lineWidth = 2;
    scrCtx.beginPath();
    scrCtx.moveTo(0, 64);
    scrCtx.lineTo(W, 64);
    scrCtx.stroke();
    scrCtx.strokeStyle = p.acc;
    scrCtx.lineWidth = 3;
    [[28, 28], [W - 28, 28], [28, H - 28], [W - 28, H - 28]].forEach(([x, y]) => {
      const dx = x < W / 2 ? 1 : -1;
      const dy = y < H / 2 ? 1 : -1;
      scrCtx.beginPath();
      scrCtx.moveTo(x + dx * 22, y);
      scrCtx.lineTo(x, y);
      scrCtx.lineTo(x, y + dy * 22);
      scrCtx.stroke();
    });

    scrCtx.textBaseline = 'alphabetic';
    scrCtx.fillStyle = p.acc;
    scrCtx.font = '600 22px ui-monospace, Consolas, monospace';
    const tag = scrState.mode === 'brief' ? 'BRIEF'
      : scrState.mode === 'result' ? 'RESULT'
        : scrState.mode === 'log' ? 'WORK LOG' : 'AI OFFICE';
    scrCtx.fillText(tag, 40, 46);

    if (scrState.mode === 'idle') {
      scrCtx.fillStyle = p.fg;
      scrCtx.font = '600 62px "Microsoft YaHei", sans-serif';
      scrCtx.fillText('今日待命', 40, 190);
      scrCtx.fillStyle = p.mut;
      scrCtx.font = '26px "Microsoft YaHei", sans-serif';
      scrCtx.fillText('点花名册右上角「简报」，或派活后看「结论」', 40, 244);
      scrCtx.fillStyle = p.line;
      scrCtx.fillRect(40, 286, W - 80, 2);
      scrCtx.fillStyle = p.mut;
      scrCtx.font = '24px ui-monospace, Consolas, monospace';
      scrCtx.fillText(`${agents.length} 名在岗 · ${night ? 'NIGHT SHIFT' : 'DAY SHIFT'}`, 40, 344);
      scrTex.needsUpdate = true;
      return;
    }

    if (scrState.mode === 'log') {
      const d = scrState.data || {};
      scrCtx.fillStyle = p.fg;
      scrCtx.font = '600 32px "Microsoft YaHei", sans-serif';
      scrCtx.fillText(String(d.title || '').slice(0, 14), 40, 104);
      scrCtx.fillStyle = d.busy ? p.acc : p.mut;
      scrCtx.font = '19px "Microsoft YaHei", sans-serif';
      scrCtx.fillText(String(d.sub || '').slice(0, 32), 40, 136);
      scrCtx.fillStyle = p.line;
      scrCtx.fillRect(40, 150, W - 80, 2);

      /* 块状 trace：色条 + 同色淡底 + 左上角"执行人 · 工具 → 目标" */
      const KC = { plan: '#3b82f6', tool: '#8b5cf6', reply: '#10b981', summary: '#e6a23c', error: '#e6542b' };
      const tint = (hex, a) => {
        const n = parseInt(hex.slice(1), 16);
        return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
      };
      const rows = (d.entries || []).slice(-4);
      let y = 168;
      rows.forEach((e) => {
        const col = KC[e.kind] || p.acc;
        const h = e.result ? 96 : 76;
        scrCtx.fillStyle = tint(col, night ? 0.2 : 0.1);
        scrCtx.beginPath();
        if (scrCtx.roundRect) scrCtx.roundRect(30, y, W - 60, h, 10);
        else scrCtx.rect(30, y, W - 60, h);
        scrCtx.fill();
        scrCtx.fillStyle = col;
        scrCtx.fillRect(30, y, 5, h);

        /* 头部：执行人 · 工具名 → 目标 */
        scrCtx.fillStyle = p.fg;
        scrCtx.font = '600 21px "Microsoft YaHei", sans-serif';
        const actor = String(e.actor || '').slice(0, 10);
        scrCtx.fillText(actor, 48, y + 30);
        let hx = 48 + scrCtx.measureText(actor).width + 10;
        if (e.tool) {
          scrCtx.fillStyle = col;
          scrCtx.font = '19px ui-monospace, Consolas, monospace';
          const tn = String(e.tool).slice(0, 20);
          scrCtx.fillText(tn, hx, y + 30);
          hx += scrCtx.measureText(tn).width + 8;
        }
        if (e.to) {
          scrCtx.fillStyle = p.mut;
          scrCtx.font = '18px "Microsoft YaHei", sans-serif';
          scrCtx.fillText('→ ' + String(e.to).slice(0, 10), hx, y + 30);
        }

        /* 正文（最多 2 行） */
        scrCtx.fillStyle = p.fg;
        scrCtx.font = '19px "Microsoft YaHei", sans-serif';
        wrapText(scrCtx, String(e.text || '').replace(/\s+/g, ' ').slice(0, 90), 48, y + 56, W - 110, 24, 2);

        /* 结果（缩进一条线 + 一行） */
        if (e.result) {
          scrCtx.fillStyle = tint(col, 0.5);
          scrCtx.fillRect(48, y + 62, 2, 24);
          scrCtx.fillStyle = p.mut;
          scrCtx.font = '17px "Microsoft YaHei", sans-serif';
          scrCtx.fillText(String(e.result).replace(/\s+/g, ' ').slice(0, 52), 58, y + 80);
        }
        y += h + 8;
      });

      if (!rows.length) {
        scrCtx.fillStyle = p.mut;
        scrCtx.font = '24px "Microsoft YaHei", sans-serif';
        scrCtx.fillText('暂无执行记录', 40, 220);
      }
      scrTex.needsUpdate = true;
      return;
    }

    if (scrState.mode === 'brief') {
      const d = scrState.data || {};
      scrCtx.fillStyle = p.fg;
      scrCtx.font = '600 40px "Microsoft YaHei", sans-serif';
      scrCtx.fillText('今日办公室简报', 40, 118);

      const cells = [
        ['派活', d.total || 0], ['协同', d.team || 0], ['单干', d.agent || 0],
        ['成员', d.people || 0], ['均耗时', `${d.avg_ms || 0}ms`], ['最近', d.last_time || '—']
      ];
      const cw = (W - 80 - 5 * 14) / 6;
      cells.forEach(([k, v], i) => {
        const x = 40 + i * (cw + 14);
        scrCtx.fillStyle = p.line;
        scrCtx.fillRect(x, 148, cw, 96);
        scrCtx.fillStyle = p.mut;
        scrCtx.font = '20px "Microsoft YaHei", sans-serif';
        scrCtx.fillText(k, x + 14, 182);
        scrCtx.fillStyle = p.fg;
        scrCtx.font = '600 34px ui-monospace, Consolas, monospace';
        scrCtx.fillText(String(v), x + 14, 224);
      });

      scrCtx.fillStyle = p.mut;
      scrCtx.font = '22px "Microsoft YaHei", sans-serif';
      scrCtx.fillText('谁最忙', 40, 292);
      const top = (d.top || []).slice(0, 3);
      const max = Math.max(1, ...top.map(t => t.count));
      top.forEach((t, i) => {
        const y = 330 + i * 66;
        scrCtx.fillStyle = p.fg;
        scrCtx.font = '26px "Microsoft YaHei", sans-serif';
        scrCtx.fillText(t.name, 40, y + 26);
        const bx = 340, bw = W - 340 - 120;
        scrCtx.fillStyle = p.line;
        scrCtx.fillRect(bx, y + 8, bw, 20);
        scrCtx.fillStyle = p.acc;
        scrCtx.fillRect(bx, y + 8, Math.max(6, bw * (t.count / max)), 20);
        scrCtx.fillStyle = p.mut;
        scrCtx.font = '600 26px ui-monospace, Consolas, monospace';
        scrCtx.fillText(String(t.count), W - 96, y + 26);
      });
      scrTex.needsUpdate = true;
      return;
    }

    /* result */
    const d = scrState.data || {};
    scrCtx.fillStyle = p.fg;
    scrCtx.font = '600 34px "Microsoft YaHei", sans-serif';
    scrCtx.fillText(String(d.title || '组长结论').slice(0, 26), 40, 116);
    scrCtx.fillStyle = p.line;
    scrCtx.fillRect(40, 136, W - 80, 2);

    scrCtx.fillStyle = p.fg;
    scrCtx.font = '30px "Microsoft YaHei", sans-serif';
    wrapText(scrCtx, d.text || '', 40, 190, W - 80, 46, 6);

    if (d.hint) {
      scrCtx.fillStyle = p.mut;
      scrCtx.font = '22px "Microsoft YaHei", sans-serif';
      scrCtx.fillText(String(d.hint).slice(0, 46), 40, H - 44);
    }
    scrTex.needsUpdate = true;
  }

  /* ================= 选中某人时的 3D 工牌（代替右侧抽屉） ================= */
  const BG_DS = 2;
  const BG_W = 512, BG_H = 344;
  const bgCv = document.createElement('canvas');
  bgCv.width = BG_W * BG_DS;
  bgCv.height = BG_H * BG_DS;
  const bgCtx = bgCv.getContext('2d');
  const bgTex = new THREE.CanvasTexture(bgCv);
  bgTex.colorSpace = THREE.SRGBColorSpace;
  bgTex.anisotropy = 8;

  const badgeMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1.72, 1.16),
    new THREE.MeshBasicMaterial({ map: bgTex, transparent: true, depthWrite: false, depthTest: false })
  );
  badgeMesh.visible = false;
  badgeMesh.renderOrder = 20;
  scene.add(badgeMesh);

  const badgeLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
    new THREE.LineBasicMaterial({ color: 0x5ec8ff, transparent: true, opacity: 0.55, depthWrite: false })
  );
  badgeLine.visible = false;
  scene.add(badgeLine);

  const badgeData = { open: false, data: null, t0: 0 };

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawBadge() {
    const d = badgeData.data || {};
    const p = scrPalette();
    bgCtx.setTransform(BG_DS, 0, 0, BG_DS, 0, 0);
    const W = BG_W, H = BG_H;
    bgCtx.clearRect(0, 0, W, H);

    /* 底板 */
    roundRect(bgCtx, 2, 2, W - 4, H - 4, 18);
    bgCtx.fillStyle = night ? 'rgba(13,21,34,0.94)' : 'rgba(255,255,255,0.95)';
    bgCtx.fill();
    bgCtx.strokeStyle = night ? 'rgba(122,190,255,0.45)' : 'rgba(47,127,214,0.35)';
    bgCtx.lineWidth = 2;
    bgCtx.stroke();

    /* 四角标记 */
    bgCtx.strokeStyle = p.acc;
    bgCtx.lineWidth = 3;
    [[16, 16], [W - 16, 16], [16, H - 16], [W - 16, H - 16]].forEach(([x, y]) => {
      const dx = x < W / 2 ? 1 : -1;
      const dy = y < H / 2 ? 1 : -1;
      bgCtx.beginPath();
      bgCtx.moveTo(x + dx * 16, y);
      bgCtx.lineTo(x, y);
      bgCtx.lineTo(x, y + dy * 16);
      bgCtx.stroke();
    });

    /* 状态 */
    const busy = d.status === 'busy';
    const wait = d.status === 'wait';
    bgCtx.fillStyle = wait ? '#e6a23c' : busy ? p.acc : p.mut;
    bgCtx.beginPath();
    bgCtx.arc(W - 92, 40, 6, 0, Math.PI * 2);
    bgCtx.fill();
    bgCtx.font = '20px "Microsoft YaHei", sans-serif';
    bgCtx.fillStyle = wait ? '#e6a23c' : busy ? p.acc : p.mut;
    bgCtx.fillText(wait ? '等你确认' : busy ? '工作中' : '在岗', W - 78, 47);

    /* 名字 + 角色 */
    bgCtx.fillStyle = p.fg;
    bgCtx.font = '600 34px "Microsoft YaHei", sans-serif';
    bgCtx.fillText(String(d.name || '').slice(0, 10), 28, 74);
    bgCtx.fillStyle = p.mut;
    bgCtx.font = '19px "Microsoft YaHei", sans-serif';
    bgCtx.fillText(String(d.role || '未设置角色').slice(0, 18), 28, 104);

    /* 分隔线 */
    bgCtx.strokeStyle = p.line;
    bgCtx.lineWidth = 1;
    bgCtx.beginPath();
    bgCtx.moveTo(28, 122);
    bgCtx.lineTo(W - 28, 122);
    bgCtx.stroke();

    /* 三行事实 */
    const rows = [
      ['角色', d.role || '未分类'],
      ['模型', d.model || '默认模型'],
      ['最近活跃', d.last || '暂无记录']
    ];
    rows.forEach(([k, v], i) => {
      const y = 158 + i * 44;
      bgCtx.fillStyle = p.mut;
      bgCtx.font = '17px "Microsoft YaHei", sans-serif';
      bgCtx.fillText(k, 28, y);
      bgCtx.fillStyle = p.fg;
      bgCtx.font = '19px "Microsoft YaHei", sans-serif';
      bgCtx.fillText(String(v).slice(0, 22), 120, y);
    });

    /* 最近执行（工作日志）：工牌下半部分 */
    const logs = d.logs || [];
    if (logs.length) {
      bgCtx.fillStyle = p.mut;
      bgCtx.font = '15px "Microsoft YaHei", sans-serif';
      bgCtx.fillText('最近', 28, H - 78);
      logs.slice(0, 2).forEach((line, i) => {
        bgCtx.fillStyle = i === 0 ? p.fg : p.mut;
        bgCtx.font = '15px "Microsoft YaHei", sans-serif';
        bgCtx.fillText(String(line).slice(0, 34), 66, H - 78 + i * 20);
      });
    }

    /* 能力标签 */
    const caps = d.caps || [];
    let cx = 28;
    const cy = H - 42;
    caps.slice(0, 4).forEach(cap => {
      bgCtx.font = '17px "Microsoft YaHei", sans-serif';
      const tw = bgCtx.measureText(cap).width + 22;
      if (cx + tw > W - 28) return;
      roundRect(bgCtx, cx, cy - 20, tw, 30, 8);
      bgCtx.fillStyle = night ? 'rgba(94,200,255,0.14)' : 'rgba(47,127,214,0.10)';
      bgCtx.fill();
      bgCtx.fillStyle = p.acc;
      bgCtx.fillText(cap, cx + 11, cy + 1);
      cx += tw + 8;
    });
    if (!caps.length) {
      bgCtx.fillStyle = p.mut;
      bgCtx.font = '17px "Microsoft YaHei", sans-serif';
      bgCtx.fillText('未绑定工具 / 技能', 28, cy + 1);
    }

    bgTex.needsUpdate = true;
  }

  function showBadge(data) {
    badgeData.data = data || null;
    badgeData.id = data && data.id != null ? data.id : selectedIdInner;
    badgeData.open = true;
    badgeData.t0 = performance.now();
    drawBadge();
    badgeMesh.visible = true;
    badgeLine.visible = true;
    badgeMesh.scale.setScalar(0.9);
    /* 镜头轻微推近到这个人（工牌才看得清） */
    const rec = badgeData.id != null ? byId.get(badgeData.id) : null;
    if (rec) {
      const p0 = rec.person.root.position;
      /* 人和大屏一起框进来：取中点，按两者距离决定缩放 */
      const sp = scrGroup.position;
      const mid = { x: (p0.x + sp.x) / 2, y: 0.9, z: (p0.z + sp.z) / 2 };
      const dist = Math.hypot(p0.x - sp.x, p0.z - sp.z);
      const zoom = Math.max(0.95, Math.min(2.1, 7.2 / Math.max(dist, 2.4)));
      /* 右侧有"执行过程"面板，把画面整体左移一点，别让面板压住大屏 */
      focusCamera(mid.x + 1.35, mid.y, mid.z, zoom);
    }
  }

  function hideBadge() {
    if (badgeData.open) restoreCamera();
    badgeData.open = false;
    badgeData.data = null;
    badgeMesh.visible = false;
    badgeLine.visible = false;
  }

  /* 聚焦：把镜头推到大屏上（关闭时退回原位） */
  const camState = { home: null, want: null };
  /* 聚焦白板/大屏时锁住 OrbitControls：不响应 update() 的阻尼回拉，也不让用户拖动抢走视角 */
  let camLock = false;

  /** 把镜头对准某点（第一次调用时记住原位） */
  function focusCamera(tx, ty, tz, zoom) {
    if (!camState.home) {
      camState.home = {
        zoom: camera.zoom,
        tx: controls.target.x, ty: controls.target.y, tz: controls.target.z
      };
    }
    camState.want = { zoom, tx, ty, tz };
  }

  /* ---------- 楼层：1F / 2F ---------- */
  let currentFloor = 1;

  function setFloor(n) {
    currentFloor = n === 2 ? 2 : 1;
    /* 没打标的一律算 1F；灯光/相机不动。用 hiddenByFloor 记住原始可见性，
       切回来时能还原（残影、工牌这类临时对象也不会被永久点亮） */
    scene.traverse(o => {
      /* 只处理"能画出来的东西"：Group 不动，否则会把另一层的子节点一起关掉 */
      if (!(o.isMesh || o.isLine || o.isSprite || o.isPoints)) return;
      const f = o.userData && o.userData.floor !== undefined ? o.userData.floor : 1;
      if (f !== currentFloor) {
        if (o.visible) {
          o.userData.hiddenByFloor = true;
          o.visible = false;
        }
      } else if (o.userData && o.userData.hiddenByFloor) {
        o.visible = true;
        o.userData.hiddenByFloor = false;
      }
    });
    refreshPlates();
    applyScreens();
  }

  function focusFloor(n, smooth = false) {
    setFloor(n);
    const ty = currentFloor === 2 ? FLOOR_H + 0.15 : 0.15;
    if (smooth) {
      /* 平滑：交给渲染循环里的 camState.want 插值（硬切会"跳"一下） */
      camState.home = null;
      camState.want = { zoom: 1, tx: 0.42, ty, tz: 0.12 };
      return;
    }
    /* 楼层切换是"硬切"：取消任何进行中的聚焦，回到默认视角 */
    camState.home = null;
    camState.want = null;
    controls.target.set(0.42, ty, 0.12);
    camera.zoom = 1;
    camera.updateProjectionMatrix();
  }

  /**
   * 镜头对准某个人（平滑推近）。点名单/名牌"定位"用。
   * - 人在另一层：先通过 onFloorSwitch 切层（让页面上的 1F/2F 也同步），再对焦
   * - 找不到这个人返回 false，调用方据此决定要不要提示
   */
  function focusAgent(name, zoom = 2.2) {
    const rec = agents.find((r) => r.data.name === name);
    if (!rec) return false;
    const wantFloor = (rec.seat && rec.seat.floor) || 1;
    if (wantFloor !== currentFloor) {
      if (opts && opts.onFloorSwitch) {
        try { opts.onFloorSwitch(wantFloor); } catch (err) { /* 回调别拖垮渲染 */ }
      } else {
        setFloor(wantFloor);
      }
    }
    const p = rec.person.root.position;
    const z = Math.max(0.9, Math.min(2.4, zoom));
    focusCamera(p.x, p.y + 0.95, p.z, z);
    return true;
  }

  /**
   * 镜头预设：overview（全景）/ board（白板）/ screen（大屏）。
   * 都走 camState.want，所以是平滑过渡；用户一拖动就被 OrbitControls 接管。
   */
  function focusWall(tx, ty, tz, cx, cy, cz, zoom) {
    /* 记录一次 home（后续回全景用），避免重复覆盖 */
    if (!camState.home) {
      camState.home = { zoom: 1, tx: 0.42, ty: currentFloor === 2 ? FLOOR_H + 0.15 : 0.15, tz: 0.12 };
    }
    /* 聚焦期间锁住 controls：不被 update() 阻尼回拉，也不让拖拽抢走 */
    camLock = true;
    controls.enabled = false;
    controls.maxZoom = Math.max(controls.maxZoom, zoom + 0.5);
    /* 白板/大屏前的健身器材挡视线：聚焦时隐藏，聚焦结束恢复 */
    setFitnessHidden(true);
    /* 立即把相机移到目标正前方并正对（正交无透视，必须移动相机才能正对墙） */
    camera.position.set(cx, cy, cz);
    controls.target.set(tx, ty, tz);
    camera.zoom = zoom;
    camera.lookAt(tx, ty, tz);
    camera.updateProjectionMatrix();
    camState.want = null;
  }
  function cameraPreset(name) {
    switch (name) {
      case 'board': {
        /* 白板在北墙：相机移到白板正南墙前方、正对过去 */
        const b = boardMesh.position;
        focusWall(b.x, b.y, b.z, b.x, b.y, b.z + 2.5, 8.5);
        return true;
      }
      case 'screen': {
        /* 大屏在北墙：相机移到大屏正南墙前方、正对过去 */
        const s = scrGroup.position;
        focusWall(s.x, s.y, s.z, s.x, s.y, s.z + 2.5, 6.0);
        return true;
      }
      case 'overview':
      case 'floor':
      default:
        camState.home = null;
        controls.maxZoom = 2.4;
        camLock = false;
        controls.enabled = true;
        setFitnessHidden(false);
        camState.want = {
          zoom: 1,
          tx: 0.42,
          ty: currentFloor === 2 ? FLOOR_H + 0.15 : 0.15,
          tz: 0.12
        };
        return true;
    }
  }

  /** 视角切换：room = 室内（默认），terrace = 拉远看露台 */
  function focusZone(zone) {
    if (zone === 'terrace') {
      focusCamera(0, 0.45, 3.2, 0.72);
    } else {
      restoreCamera();
    }
  }

  /** 退回原位 */
  function restoreCamera() {
    if (!camState.home) return;
    camState.want = camState.home;
    camState.home = null;
    controls.maxZoom = 2.4;
    camLock = false;
    controls.enabled = true;
    setFitnessHidden(false);
  }

  function focusScreen(on) {
    if (on) {
      const s = scrGroup.position;
      focusWall(s.x, s.y, s.z, s.x, s.y, s.z + 2.5, 6.0);
      scrGlow.intensity = night ? 2.4 : 0;
    } else {
      restoreCamera();
      scrGlow.intensity = 0;
    }
  }

  /** 外部入口：mode = 'brief' | 'result' | 'idle' */
  function setScreen(mode, data, opts) {
    scrState.mode = mode || 'idle';
    scrState.data = data || null;
    drawScreen();
    if (!opts || opts.focus !== false) focusScreen(mode !== 'idle');
  }

  function closeScreen() {
    if (scrState.mode === 'idle') return;
    scrState.mode = 'idle';
    scrState.data = null;
    drawScreen();
    focusScreen(false);
  }

  /* ================= 露台（第二办公区，室外） ================= */
  const TERZ = 6.62;           // 露台中心 z（紧贴室内地板 z=4.75）
  {
    /* 木地板 + 一圈台阶边 */
    B(8.6, 0.10, 3.6, M.wood, 0, -0.02, TERZ, 0.02, { cast: false });
    B(8.7, 0.05, 0.16, M.deskEdge, 0, 0.03, TERZ - 1.82, 0.01, { cast: false });
    B(0.16, 0.05, 3.7, M.deskEdge, -4.32, 0.03, TERZ, 0.01, { cast: false });
    B(0.16, 0.05, 3.7, M.deskEdge, 4.32, 0.03, TERZ, 0.01, { cast: false });
    /* 栏杆：立柱 + 玻璃 + 扶手 */
    for (let x = -4.3; x <= 4.31; x += 1.075) {
      B(0.05, 0.86, 0.05, M.frame, x, 0.45, TERZ + 1.78, 0.01, { cast: false });
    }
    B(8.7, 0.02, 0.02, M.glass, 0, 0.72, TERZ + 1.78, 0.004, { cast: false });
    B(8.7, 0.04, 0.06, M.frame, 0, 0.9, TERZ + 1.78, 0.01, { cast: false });

    /* 三把遮阳伞 + 桌子 + 凳子 */
    const parasol = (x, z) => {
      C(0.03, 0.03, 1.62, M.frame, x, 0.82, z, 10, { cast: false });
      const cone = mesh(new THREE.ConeGeometry(1.05, 0.42, 14, 1, true), M.parasol,
        x, 1.72, z, { cast: false, receive: false });
      cone.material.side = THREE.DoubleSide;
    };
    [-2.9, 0, 2.9].forEach((x, i) => {
      const z = TERZ + (i % 2 ? 0.5 : -0.2);
      parasol(x, z);
      C(0.42, 0.42, 0.05, M.wood, x, 0.76, z, 20, { cast: false });
      C(0.05, 0.05, 0.74, M.metal, x, 0.38, z, 8, { cast: false });
      C(0.26, 0.26, 0.03, M.metal, x, 0.04, z, 16, { cast: false });
      /* 两个高脚凳 */
      [-0.62, 0.62].forEach(dz => stool(x, z + dz, 0.64));
    });

    /* 夜里：栏杆上挂一串小灯（用自发光小球，成本极低） */
    for (let i = 0; i < 14; i++) {
      const x = -4.2 + i * 0.65;
      const y = 0.92 + Math.sin(i * 0.9) * 0.06;
      S(0.028, M.bulb, x, y, TERZ + 1.76, { cast: false, receive: false });
    }
    /* 角落绿植 */
    plant(-3.9, TERZ + 1.35, 1.15);
    plant(3.9, TERZ + 1.35, 1.15);
  }

  /* ================= 咖啡吧 ================= */
  B(3.0, 0.96, 0.68, M.desk, 4.2, 0.48, 2.0, 0.03);
  B(3.12, 0.05, 0.78, M.wood, 4.2, 0.985, 2.0, 0.02);
  B(2.9, 0.45, 0.02, M.deskEdge, 4.2, 0.55, 2.348, 0.01, { cast: false });
  B(0.68, 0.96, 1.5, M.desk, 5.78, 0.48, 1.3, 0.03);
  B(0.78, 0.05, 1.58, M.wood, 5.78, 0.985, 1.3, 0.02);
  /* 踢脚灯带 */
  B(2.7, 0.02, 0.02, M.led, 4.2, 0.06, 2.36, 0.005, { cast: false });
  B(0.02, 0.02, 1.3, M.led, 5.47, 0.06, 1.3, 0.005, { cast: false });

  /* 咖啡机 */
  B(0.38, 0.36, 0.34, M.desk, 5.05, 1.19, 2.0, 0.02);
  B(0.4, 0.05, 0.36, M.darkMetal, 5.05, 1.39, 2.0, 0.015);
  B(0.12, 0.07, 0.12, M.metal, 5.05, 1.31, 2.18, 0.01);
  C(0.045, 0.045, 0.06, M.darkMetal, 5.05, 1.31, 2.12, 12);
  B(0.3, 0.015, 0.12, M.metal, 5.05, 1.02, 2.14, 0.005);
  C(0.038, 0.034, 0.07, M.ceramic, 5.05, 1.06, 2.14, 14);
  B(0.1, 0.06, 0.01, M.screenSmall, 5.05, 1.24, 2.19, 0.004, { cast: false });
  /* 磨豆机 */
  C(0.07, 0.07, 0.16, M.darkMetal, 4.62, 1.1, 2.02, 16);
  C(0.055, 0.055, 0.08, M.glass, 4.62, 1.22, 2.02, 16);

  /* 托盘 + 杯 + 碟 */
  B(0.3, 0.015, 0.2, M.wood, 3.72, 1.02, 2.1, 0.008, { cast: false });
  C(0.042, 0.038, 0.08, M.ceramic, 3.66, 1.06, 2.08, 16);
  C(0.042, 0.038, 0.08, M.ceramic, 3.78, 1.06, 2.12, 16);
  C(0.12, 0.11, 0.02, M.ceramic, 4.55, 1.02, 1.86, 20);
  B(0.2, 0.12, 0.012, M.paper, 4.9, 1.14, 1.72, 0.004, { rx: -0.2, cast: false }); /* 菜单牌 */

  /* 吧台上的马克杯（正对两个座位） */
  [[3.5, 2.14], [4.7, 2.14]].forEach(([mx, mz]) => {
    const mug = std('#5f7185', { r: 0.45 });
    mesh(new THREE.CylinderGeometry(0.038, 0.032, 0.085, 18), mug, mx, 1.07, mz, { cast: false });
    mesh(new THREE.CylinderGeometry(0.033, 0.033, 0.008, 18), std('#3f2f24', { r: 0.5 }), mx, 1.115, mz, { cast: false });
    const h = mesh(new THREE.TorusGeometry(0.024, 0.007, 6, 10, Math.PI * 1.2), mug, mx + 0.038, 1.072, mz, { cast: false });
    h.rotation.y = Math.PI / 2;
  });

  /* 高脚凳（4 条外撇腿 + 脚圈，座高 0.64 与 coffee 坐姿匹配） */
  [[3.5, 2.95], [4.7, 2.95], [5.85, 2.62]].forEach(([x, z]) => stool(x, z, 0.64));

  /* ================= 健身角 ================= */
  /* 这些器材摆在大屏/白板正前方，聚焦看大屏/白板时会被它们挡住。
     用 group 记录，聚焦时隐藏，聚焦结束恢复。 */
  const FITNESS = new THREE.Group();
  FITNESS.userData.fitness = true;
  scene.add(FITNESS);
  { B(0.92, 0.16, 1.86, M.desk, -5.5, 0.09, -3.35, 0.03, { parent: FITNESS });
  B(0.62, 0.02, 1.42, M.dark, -5.5, 0.18, -3.3, 0.01, { cast: false, parent: FITNESS });
  B(0.07, 0.05, 1.7, M.metal, -5.95, 0.2, -3.3, 0.015, { parent: FITNESS });
  B(0.07, 0.05, 1.7, M.metal, -5.05, 0.2, -3.3, 0.015, { parent: FITNESS });
  C(0.03, 0.03, 0.95, M.metal, -5.85, 0.7, -4.14, 10, { parent: FITNESS });
  C(0.03, 0.03, 0.95, M.metal, -5.15, 0.7, -4.14, 10, { parent: FITNESS });
  B(0.78, 0.28, 0.07, M.darkMetal, -5.5, 1.14, -4.16, 0.02, { rx: 0.28, parent: FITNESS });
  B(0.5, 0.16, 0.01, M.screen, -5.5, 1.15, -4.12, 0.008, { rx: 0.28, cast: false, parent: FITNESS });
  /* 哑铃架 */
  B(1.24, 0.05, 0.3, M.desk, -3.55, 0.44, -4.1, 0.015, { parent: FITNESS });
  B(1.24, 0.05, 0.3, M.desk, -3.55, 0.74, -4.1, 0.015, { parent: FITNESS });
  [[-0.56], [0.56]].forEach(([dx]) => B(0.05, 0.78, 0.05, M.metal, -3.55 + dx, 0.39, -4.1, 0.012, { parent: FITNESS }));
  [[-0.4, 0.5], [0, 0.5], [0.4, 0.5], [-0.2, 0.8], [0.2, 0.8]].forEach(([dx, y]) => {
    C(0.055, 0.055, 0.16, M.darkMetal, -3.55 + dx, y, -4.1, 12, { rz: Math.PI / 2, parent: FITNESS });
    C(0.075, 0.075, 0.03, M.dark, -3.55 + dx - 0.08, y, -4.1, 12, { rz: Math.PI / 2, parent: FITNESS });
    C(0.075, 0.075, 0.03, M.dark, -3.55 + dx + 0.08, y, -4.1, 12, { rz: Math.PI / 2, parent: FITNESS });
  });
  B(0.8, 0.02, 1.6, M.accent, -3.4, 0.09, -2.55, 0.01, { cast: false, parent: FITNESS }); }
  /* 记录每条健身器材的原始可见性，聚焦时统一隐藏、结束恢复 */
  const fitnessVis = [];
  FITNESS.traverse(o => { if (o.isMesh) fitnessVis.push([o, o.visible]); });
  function setFitnessHidden(hide) {
    fitnessVis.forEach(([o, v]) => { o.visible = hide ? false : v; });
  }

  /* ================= 休息区 ================= */
  B(2.3, 0.3, 0.92, M.chair, -0.4, 0.24, 3.55, 0.05);
  B(1.06, 0.15, 0.84, M.chair, -0.95, 0.46, 3.55, 0.05);
  B(1.06, 0.15, 0.84, M.chair, 0.15, 0.46, 3.55, 0.05);
  B(2.3, 0.52, 0.2, M.chair, -0.4, 0.63, 3.86, 0.05);
  B(1.0, 0.3, 0.15, M.chairDark, -0.95, 0.62, 3.75, 0.05);
  B(1.0, 0.3, 0.15, M.chairDark, 0.15, 0.62, 3.75, 0.05);
  B(0.18, 0.48, 0.92, M.chair, -1.62, 0.42, 3.55, 0.05);
  B(0.18, 0.48, 0.92, M.chair, 0.82, 0.42, 3.55, 0.05);
  C(0.44, 0.44, 0.05, M.wood, 1.95, 0.41, 3.55, 32);
  C(0.06, 0.06, 0.36, M.metal, 1.95, 0.22, 3.55, 12);
  C(0.26, 0.28, 0.03, M.metal, 1.95, 0.035, 3.55, 24);
  B(0.22, 0.03, 0.3, M.paper, 1.82, 0.45, 3.5, 0.005, { ry: 0.3 });
  B(0.22, 0.02, 0.3, M.paper, 1.84, 0.47, 3.52, 0.005, { ry: 0.18 });
  C(0.04, 0.036, 0.08, M.ceramic, 2.12, 0.475, 3.62, 14);
  /* 绿植 */
  C(0.22, 0.17, 0.4, M.pot, -2.6, 0.24, 3.3, 24);
  C(0.19, 0.19, 0.03, M.dark, -2.6, 0.44, 3.3, 20, { cast: false });
  for (let i = 0; i < 11; i++) {
    const a = i / 11 * Math.PI * 2 + 0.3;
    const rr = 0.18 + (i % 3) * 0.09;
    const leaf = mesh(new THREE.SphereGeometry(0.18, 12, 10), M.plant,
      -2.6 + Math.cos(a) * rr, 0.6 + (i % 4) * 0.13, 3.3 + Math.sin(a) * rr, { rx: 0.2, ry: a });
    leaf.scale.set(0.9, 0.42, 1.5);
  }

  /* ================= 落地绿植 ×2 ================= */
  function floorPlant(x, z, sc) {
    sc = sc || 1;
    C(0.2 * sc, 0.16 * sc, 0.42 * sc, M.pot, x, 0.21 * sc, z, 20);
    C(0.17 * sc, 0.17 * sc, 0.02 * sc, M.dark, x, 0.42 * sc, z, 16, { cast: false });
    for (let i = 0; i < 9; i++) {
      const a = i / 9 * Math.PI * 2 + 0.6;
      const rr = 0.14 * sc + (i % 3) * 0.07 * sc;
      const leaf = mesh(new THREE.SphereGeometry(0.16 * sc, 10, 8), M.plant,
        x + Math.cos(a) * rr, (0.58 + (i % 4) * 0.11) * sc, z + Math.sin(a) * rr,
        { rx: 0.2, ry: a });
      leaf.scale.set(0.85, 0.38, 1.4);
    }
  }
  floorPlant(3.05, 1.05, 0.95);
  floorPlant(6.55, -1.15, 0.85);

  /* ================= 书柜 ================= */
  {
    const BX = -6.24, BZ = -0.4, BW = 0.32, BH = 1.72, BD = 1.9;
    B(BW, BH, 0.04, M.desk, BX, BH / 2, BZ - BD / 2, 0.01);
    B(BW, BH, 0.04, M.desk, BX, BH / 2, BZ + BD / 2, 0.01);
    B(0.04, BH, BD, M.desk, BX - BW / 2 + 0.02, BH / 2, BZ, 0.01);
    B(BW, 0.04, BD, M.desk, BX, BH - 0.02, BZ, 0.01);
    [0.02, 0.44, 0.86, 1.28].forEach((y, si) => {
      B(BW - 0.02, 0.03, BD - 0.06, M.desk, BX, y + 0.1, BZ, 0.008);
      let z = BZ - BD / 2 + 0.1;
      for (let i = 0; i < 11; i++) {
        const w = 0.035 + ((i * 37 + si * 13) % 5) * 0.006;
        const h = 0.24 + ((i * 29 + si * 7) % 4) * 0.03;
        const mat = i % 3 === 0 ? M.chairDark : (i % 3 === 1 ? M.paper : M.metal);
        B(BW - 0.1, h, w, mat, BX + 0.02, y + 0.12 + h / 2, z + w / 2, 0.004, { cast: false });
        z += w + 0.012;
      }
      /* 架上杂物 */
      if (si === 1) {
        B(0.16, 0.06, 0.22, M.woodDark, BX + 0.02, y + 0.16, BZ + 0.62, 0.01);
        B(0.16, 0.05, 0.2, M.paper, BX + 0.02, y + 0.215, BZ + 0.62, 0.008, { cast: false });
      }
      if (si === 3) {
        C(0.06, 0.05, 0.12, M.pot, BX + 0.02, y + 0.19, BZ - 0.6, 14);
        S(0.09, M.plant, BX + 0.02, y + 0.3, BZ - 0.6);
      }
    });
  }

  /* ================= 卫生间 ================= */
  const TX = -6.0, TZ = 2.7;
  B(1.46, 0.02, 1.86, M.carpet, TX, 0.05, TZ, 0.02, { cast: false });
  B(0.1, 1.5, 1.86, M.wall, TX - 0.73, 0.75, TZ, 0.02, { cast: false });
  B(1.46, 1.5, 0.1, M.wall, TX, 0.75, TZ - 0.93, 0.02, { cast: false });
  B(0.5, 1.5, 0.1, M.wall, TX + 0.48, 0.75, TZ + 0.93, 0.02, { cast: false });
  B(0.58, 1.5, 0.1, M.wall, TX - 0.44, 0.75, TZ + 0.93, 0.02, { cast: false });
  B(0.42, 1.42, 0.05, M.paper, TX - 0.1, 0.72, TZ + 0.9, 0.01, { ry: -0.35 });
  B(0.03, 0.1, 0.03, M.metal, TX + 0.06, 0.72, TZ + 0.88, 0.008);
  B(0.34, 0.34, 0.46, M.ceramic, TX - 0.34, 0.17, TZ - 0.55, 0.04);
  C(0.19, 0.16, 0.1, M.ceramic, TX - 0.34, 0.4, TZ - 0.45, 20);
  B(0.34, 0.3, 0.13, M.ceramic, TX - 0.34, 0.5, TZ - 0.78, 0.03);
  B(0.44, 0.1, 0.34, M.ceramic, TX + 0.38, 0.78, TZ - 0.6, 0.03);
  C(0.12, 0.1, 0.06, M.pot, TX + 0.38, 0.85, TZ - 0.6, 18);
  B(0.4, 0.5, 0.02, M.glass, TX + 0.38, 1.12, TZ - 0.86, 0.01, { cast: false });
  C(0.145, 0.145, 0.012, M.paper, TX - 0.34, 0.72, TZ - 0.55, 20, { cast: false });

  /* ================= 墙角阴影（假 AO） ================= */
  {
    const grad = (dir) => {
      const cv = document.createElement('canvas');
      cv.width = 4; cv.height = 128;
      const ctx = cv.getContext('2d');
      const g = ctx.createLinearGradient(0, dir ? 128 : 0, 0, dir ? 0 : 128);
      g.addColorStop(0, 'rgba(40,48,62,0.42)');
      g.addColorStop(1, 'rgba(40,48,62,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 4, 128);
      return new THREE.CanvasTexture(cv);
    };
    const strip = (w, d, x, z, tex, ry) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d),
        new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.5, depthWrite: false }));
      m.rotation.x = -Math.PI / 2;
      if (ry) m.rotation.z = ry;
      m.position.set(x, 0.058, z);
      scene.add(m);
    };
    /* 北墙根 */
    strip(FW, 0.75, 0, -FD / 2 + 0.36, grad(true), 0);
    /* 西墙根 */
    strip(0.75, FD, -FW / 2 + 0.36, 0, grad(true), Math.PI / 2);
  }

  /* ================= 接触阴影 ================= */
  {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 256;
    const ctx = cv.getContext('2d');
    const grd = ctx.createRadialGradient(128, 128, 8, 128, 128, 126);
    grd.addColorStop(0, 'rgba(24,32,46,1)');
    grd.addColorStop(0.45, 'rgba(24,32,46,0.55)');
    grd.addColorStop(1, 'rgba(24,32,46,0)');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, 256, 256);
    const tex = new THREE.CanvasTexture(cv);
    const contact = (x, z, w, d, op) => {
      const m = new THREE.Mesh(
        new THREE.PlaneGeometry(w, d),
        new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: op, depthWrite: false })
      );
      m.rotation.x = -Math.PI / 2;
      m.position.set(x, 0.056, z);
      scene.add(m);
    };
    DESKS.forEach(d => contact(d.x, d.z + 0.28, 2.0, 1.45, 0.13));
    contact(-3.9, 2.55, 3.0, 1.15, 0.13);
    contact(4.8, -3.1, 3.5, 3.5, 0.09);
    contact(4.9, 1.7, 3.8, 1.5, 0.12);
    [[3.5, 2.95], [4.7, 2.95], [5.85, 2.62]].forEach(([x, z]) => contact(x, z, 0.62, 0.62, 0.15));
    contact(-0.4, 3.55, 3.0, 1.35, 0.13);
    contact(1.95, 3.55, 1.15, 1.15, 0.11);
    contact(-2.6, 3.3, 0.8, 0.8, 0.13);
    contact(-5.5, -3.35, 1.35, 2.25, 0.13);
    contact(-3.55, -4.1, 1.55, 0.6, 0.12);
    contact(-3.4, -2.55, 1.0, 1.9, 0.05);
    contact(-6.0, 2.4, 1.6, 1.5, 0.10);
    contact(-6.24, -0.4, 0.7, 2.1, 0.12);
  }

  /* ================= 协作光束（组长 → 在忙的组员） ================= */
  const BEAM_N = 16;      // 每条弧线的分段数
  const BEAM_MAX = 10;    // 最多同时画几条
  const BEAMS = [];
  {
    const lineMat = new THREE.LineBasicMaterial({ color: 0x409eff, transparent: true, opacity: 0.85 });
    const dotMat = new THREE.MeshStandardMaterial({ color: 0x409eff, emissive: 0x2f86e0, emissiveIntensity: 0.7 });
    for (let i = 0; i < BEAM_MAX; i++) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(3 * BEAM_N), 3));
      const line = new THREE.Line(geo, lineMat);
      line.visible = false;
      scene.add(line);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), dotMat);
      dot.visible = false;
      scene.add(dot);
      BEAMS.push({ line, dot, geo });
    }
  }

  /* ================= 失败光束（组长 → 出事的人，红色虚线弧） ================= */
  let failTarget = null;
  let failUntil = 0;
  const FAIL_N = 16;
  const failGeo = new THREE.BufferGeometry();
  failGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(3 * FAIL_N), 3));
  const failLine = new THREE.Line(
    failGeo,
    new THREE.LineDashedMaterial({ color: 0xe05a3c, dashSize: 0.18, gapSize: 0.12, transparent: true, opacity: 0.95 })
  );
  failLine.visible = false;
  scene.add(failLine);
  const failDot = new THREE.Mesh(
    new THREE.SphereGeometry(0.06, 12, 10),
    new THREE.MeshStandardMaterial({ color: 0xe05a3c, emissive: 0xc0442b, emissiveIntensity: 0.9 })
  );
  failDot.visible = false;
  scene.add(failDot);

  /* 出事的人脚下脉动红圈：1px 虚线在小比例下太淡，加一圈才看得见 */
  const failRing = new THREE.Mesh(
    new THREE.RingGeometry(0.3, 0.44, 36),
    new THREE.MeshBasicMaterial({
      color: 0xe05a3c, transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthWrite: false
    })
  );
  failRing.rotation.x = -Math.PI / 2;
  failRing.visible = false;
  scene.add(failRing);

  /** 出事：从组长拉一条红弧到这个人，默认 4 秒后消失 */
  function failBeam(name, seconds = 4) {
    const rec = agents.find(r => r.data && r.data.name === name);
    if (!rec || rec.data.isLeader) return;
    failTarget = rec;
    failUntil = performance.now() + Math.max(1, seconds) * 1000;
  }

  /* ================= 协同可视化：派活 → 任务线 + 受命/等待标记 ================= */
  const HANDOFFS = [];

  /** 组长派活给某人：从组长头顶拉一条弧线到组员头顶，一个光点沿弧线飞过去 */
  /**
   * 两人之间拉一条弧线 + 流动光点。
   * `color`：派活蓝 0x3b82f6 / 回话绿 0x22c55e；`life` 毫秒。
   */
  function _beam(a, b, color, life) {
    if (!a || !b || a === b) return;
    const p0 = new THREE.Vector3();
    const p1 = new THREE.Vector3();
    headWorldPos(a, p0);
    headWorldPos(b, p1);
    p0.y += 0.08;
    p1.y += 0.08;
    const mid = p0.clone().add(p1).multiplyScalar(0.5);
    mid.y = Math.max(p0.y, p1.y) + 0.85;
    const curve = new THREE.QuadraticBezierCurve3(p0, mid, p1);
    /* 用细管而不是 Line：Line 在多数显卡上只有 1px，远看几乎看不见 */
    const geo = new THREE.TubeGeometry(curve, 24, 0.014, 6, false);
    const line = new THREE.Mesh(
      geo,
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, depthWrite: false })
    );
    line.frustumCulled = false;
    scene.add(line);
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(0.075, 12, 10),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 1 })
    );
    scene.add(dot);
    /* 任务线只属于某一层：切到别的楼层时不能悬在半空 */
    const hf = (b.seat && b.seat.floor) || 1;
    line.userData.floor = hf;
    dot.userData.floor = hf;
    if (hf !== currentFloor) {
      line.visible = false;
      dot.visible = false;
    }
    HANDOFFS.push({ line, dot, curve, t0: performance.now(), life });
  }

  function handoff(fromName, toName) {
    const a = agents.find(r => r.data && r.data.name === fromName);
    const b = agents.find(r => r.data && r.data.name === toName);
    if (!a || !b || a === b) return;
    _beam(a, b, 0x3b82f6, 3000);

    /* 名牌上标出来：组员"受命于谁"、组长"在等谁" */
    b.assignedBy = fromName;
    b.assignedUntil = nowT + 14;
    a.awaiting = toName;
    a.awaitingList = (a.awaitingList || []).filter((n) => n !== toName);
    a.awaitingList.push(toName);          // 并行派活时记下"在等几个人"
    a.awaitingUntil = nowT + 14;
    refreshPlates();
  }

  /** 组员回话：清掉受命/等待标记，并拉一条返程绿线（成员 → 派活给他的人） */
  function replyDone(name) {
    const me = agents.find((r) => r.data && r.data.name === name);
    if (me) {
      const back = me.assignedBy
        ? agents.find((r) => r.data && r.data.name === me.assignedBy)
        : agents.find((r) => r.data && r.data.isLeader);
      /* 返程线：从回话的人飞回组长（或派活给他的人） */
      if (back) _beam(me, back, 0x22c55e, 2200);
    }
    let dirty = false;
    agents.forEach((r) => {
      if (r.data && r.data.name === name && r.assignedBy) {
        r.assignedBy = null;
        dirty = true;
      }
      if (r.awaitingList && r.awaitingList.includes(name)) {
        r.awaitingList = r.awaitingList.filter((n) => n !== name);
        r.awaiting = r.awaitingList[r.awaitingList.length - 1] || null;
        dirty = true;
      } else if (r.awaiting === name) {
        r.awaiting = null;
        dirty = true;
      }
    });
    if (dirty) refreshPlates();
  }

  /** 组长走过去派活：临时走到组员身边站 3 秒，再走回原位（跨楼层不去，避免瞬移） */
  function leaderVisit(toName) {
    const leader = agents.find(r => r.data && r.data.isLeader);
    const target = agents.find(r => r.data && r.data.name === toName);
    if (!leader || !target || leader === target) return;
    const lf = leader.person.root.userData.floor || 1;
    const tf = target.person.root.userData.floor || 1;
    if (lf !== tf) return;
    const home = {
      x: leader.person.root.position.x,
      z: leader.person.root.position.z,
      ry: leader.person.root.rotation.y
    };
    const p = target.person.root.position;
    const ang = (target.person.root.rotation.y || 0) + Math.PI / 2;
    const gx = p.x + Math.sin(ang) * 0.62;
    const gz = p.z + Math.cos(ang) * 0.62;
    leader.visiting = true;
    walkTo(leader, gx, gz, Math.atan2(p.x - gx, p.z - gz), 'stand', () => {
      window.setTimeout(() => {
        walkTo(leader, home.x, home.z, home.ry, 'stand', () => {
          leader.visiting = false;
        });
      }, 3000);
    });
  }

  /** 长任务中途同步：大家回白板前站 5 秒，组长冒一句"同步下进度" */
  function midSync(names, text) {
    const list = (names || []).filter(Boolean);
    if (!list.length) return;
    gatherAtBoard(list, 5000);
    const leader = agents.find(r => r.data && r.data.isLeader);
    if (leader) {
      say({ from: leader.data.name, text: text || '同步一下进度，大家对一下手上的结果', kind: 'delegate' });
    }
  }

  /** 汇总时全员围到白板前听组长讲结论 */
  function gatherAtBoard(names, ms = 9000) {
    const spots = [
      [-5.30, -3.02], [-4.78, -2.86], [-4.28, -2.80], [-3.92, -3.06], [-4.60, -3.34]
    ];
    const movers = [];
    (names || []).forEach((nm, i) => {
      const r = agents.find(x => x.data && x.data.name === nm);
      if (!r) return;
      const s0 = spots[i % spots.length];
      movers.push(r);
      walkTo(r, s0[0], s0[1], Math.PI, 'stand', () => {
        lookAtPoint(r, -4.7, -3.9, Math.ceil(ms / 1000));
      });
    });
    if (!movers.length) return;
    window.setTimeout(() => {
      movers.forEach((r) => {
        if (r.seat) moveTo(r, r.seat);
      });
    }, ms);
  }

  /** 每帧推进任务线（光点在弧线上跑，线逐渐淡出） */
  function tickHandoffs() {
    for (let i = HANDOFFS.length - 1; i >= 0; i--) {
      const h = HANDOFFS[i];
      const k = (performance.now() - h.t0) / h.life;
      if (k >= 1) {
        scene.remove(h.line);
        scene.remove(h.dot);
        h.line.geometry.dispose();
        h.line.material.dispose();
        h.dot.geometry.dispose();
        h.dot.material.dispose();
        HANDOFFS.splice(i, 1);
        continue;
      }
      h.line.material.opacity = 0.9 * (1 - k * 0.75);
      const t = Math.min(1, k * 2.4);
      h.dot.position.copy(h.curve.getPoint(t));
      h.dot.material.opacity = 1 - Math.max(0, (k - 0.55) / 0.45);
      h.dot.scale.setScalar(1 - 0.45 * Math.max(0, k - 0.4));
    }
  }

  /* ================= 高亮块 / 走动残影 ================= */
  const HL = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ color: 0x409eff, transparent: true, opacity: 0.12, depthWrite: false })
  );
  HL.rotation.x = -Math.PI / 2;
  HL.position.y = 0.062;
  HL.visible = false;
  scene.add(HL);

  const TRAIL_N = 26;
  const TRAILS = [];
  for (let i = 0; i < TRAIL_N; i++) {
    const m = new THREE.Mesh(
      new THREE.CircleGeometry(0.09, 12),
      new THREE.MeshBasicMaterial({ color: 0x409eff, transparent: true, opacity: 0, depthWrite: false })
    );
    m.rotation.x = -Math.PI / 2;
    m.position.y = 0.064;
    m.visible = false;
    scene.add(m);
    TRAILS.push({ m, life: 0 });
  }
  let trailIdx = 0;

  /* 这些是"一层的界面元素"：残影、选中高亮、工牌、引线、大屏 —— 切楼层时一起藏 */
  HL.userData.floor = 1;
  TRAILS.forEach(t => { t.m.userData.floor = 1; });
  badgeMesh.userData.floor = 1;
  badgeLine.userData.floor = 1;
  scrMesh.userData.floor = 1;

  /* ================= 人物（带关节） ================= */
  /* ================= 卡通人物 ================= */
  const SKIN = std('#f2d3bd', { r: 0.72 });
  const EYE = std('#2c333d', { r: 0.35 });
  const MOUTH = std('#b4736a', { r: 0.6 });
  const SHOE = std('#39414d', { r: 0.7 });

  /* 每人一套衣服配色：衬衫 / 裤子 / 头发 */
  /* 衣服纹理：细条纹（灰度，乘上衬衫色） */
  const stripeTex = (() => {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 64;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 64, 64);
    ctx.fillStyle = 'rgba(0,0,0,0.07)';
    for (let i = 0; i < 64; i += 8) ctx.fillRect(i, 0, 3.5, 64);
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(7, 7);
    return t;
  })();

  const LOOK = {
    '阿棠': ['#3b82f6', '#334155', '#2f343d', 'short', 'plain'],
    '沈知': ['#8b5cf6', '#3f3f46', '#3a3129', 'bun', 'stripe'],
    '苏末': ['#f59e0b', '#44403c', '#4a3a2c', 'long', 'knit'],
    '白露': ['#10b981', '#334155', '#584a3c', 'side', 'plain'],
    '江屿': ['#0ea5e9', '#3f4650', '#2c323b', 'short', 'stripe'],
    '顾行': ['#f97362', '#3f3f46', '#332e28', 'bowl', 'knit'],
    '闻笙': ['#ec4899', '#3d4550', '#2f3540', 'bun', 'plain']
  };
  /* 没登记名字的人：按名字哈希从调色板里挑一套（同一人永远同一套） */
  const PALETTE = {
    shirt: ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#0ea5e9', '#f97362',
      '#ec4899', '#14b8a6', '#eab308', '#6366f1', '#ef4444', '#64748b'],
    pants: ['#334155', '#3f3f46', '#44403c', '#3d4550', '#2f3a4a', '#4b5563',
      '#1f2937', '#6b7280'],
    hair: ['#2f343d', '#3a3129', '#4a3a2c', '#584a3c', '#2c323b', '#332e28', '#5b4636', '#8a6a4a'],
    shoe: ['#39414d', '#2b303a', '#5b4636', '#e8ecf2', '#8b5a3c', '#3b4a5e'],
    style: ['short', 'side', 'bowl', 'bun', 'long'],
    pat: ['plain', 'stripe', 'knit']
  };
  const hashOf = (str) => {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h >>> 0;
  };
  const pick = (arr, h, shift) => arr[(h >>> shift) % arr.length];

  const lookCache = {};
  const lookOf = (name) => {
    if (!lookCache[name]) {
      let c = LOOK[name];
      if (!c) {
        const h = hashOf(name || 'x');
        c = [
          pick(PALETTE.shirt, h, 0),
          pick(PALETTE.pants, h, 4),
          pick(PALETTE.hair, h, 8),
          pick(PALETTE.style, h, 12),
          pick(PALETTE.pat, h, 16),
          pick(PALETTE.shoe, h, 20)
        ];
      }
      const shirtMat = std(c[0], { r: 0.88 });
      const kind = c[4] || 'plain';
      if (kind === 'knit') {
        const t = texLoader.load(TEXDATA.fabric);
        t.wrapS = t.wrapT = THREE.MirroredRepeatWrapping;
        t.repeat.set(5, 5);
        shirtMat.bumpMap = t;
        shirtMat.bumpScale = 0.012;
        shirtMat.needsUpdate = true;
      } else if (kind === 'stripe') {
        const t = stripeTex.clone();
        t.needsUpdate = true;
        t.repeat.set(9, 9);
        shirtMat.bumpMap = t;
        shirtMat.bumpScale = 0.01;
        shirtMat.needsUpdate = true;
      }
      const sleeve = shirtMat.clone();
      sleeve.color = new THREE.Color(c[0]).multiplyScalar(0.86);
      lookCache[name] = {
        shirt: shirtMat,
        sleeve,
        pants: std(c[1], { r: 0.9 }),
        hair: std(c[2], { r: 0.82 }),
        style: c[3] || 'short',
        shoe: std(c[5] || '#39414d', { r: 0.72 }),
        colors: c,   // [shirt, pants, hair, style, pattern, shoe]
        /* 细节：领口比衬衫深一点，腰带比裤子深一点，鞋底浅一档 */
        collar: std(new THREE.Color(c[0]).multiplyScalar(0.78).getStyle(), { r: 0.8 }),
        belt: std(new THREE.Color(c[1]).multiplyScalar(0.62).getStyle(), { r: 0.6 }),
        sole: std('#dfe5ee', { r: 0.85 })
      };
    }
    return lookCache[name];
  };

  /**
   * 换一个人的造型：只换材质引用，不重建模型（几十个人时也是瞬时）。
   * patch: { shirt, pants, hair, style, shoe, pat }
   */
  function setLook(name, patch) {
    const oldLook = lookOf(name);
    const c = oldLook.colors || [];
    const next = [
      (patch && patch.shirt) || c[0],
      (patch && patch.pants) || c[1],
      (patch && patch.hair) || c[2],
      (patch && patch.style) || c[3] || 'short',
      (patch && patch.pat) || c[4] || 'plain',
      (patch && patch.shoe) || c[5] || '#39414d'
    ];
    LOOK[name] = next;
    delete lookCache[name];
    const newLook = lookOf(name);
    const keys = ['shirt', 'sleeve', 'pants', 'hair', 'shoe', 'collar', 'belt', 'sole'];
    agents.filter(r => r.data.name === name).forEach(rec => {
      rec.person.root.traverse(o => {
        if (!o.material) return;
        for (const k of keys) {
          if (o.material === oldLook[k]) { o.material = newLook[k]; break; }
        }
      });
    });
    return next;
  }

  const SEATED_POSES = new Set(['sit', 'sitback', 'work', 'coffee']);

  const POSES = {
    stand:  { hip: 0.70, thigh: 0.02, knee: 0.02, foot: -0.04, arm: 0.06, elbow: -0.10, torso: 0, head: 0 },
    walk:   { hip: 0.70, thigh: 0.02, knee: 0.02, foot: -0.04, arm: 0.06, elbow: -0.10, torso: 0, head: 0 },
    work:   { hip: 0.615, thigh: -1.45, knee: 1.42, foot: 0.03, arm: -1.34, elbow: -0.52, torso: 0.10, head: 0.14 },
    sit:    { hip: 0.615, thigh: -1.30, knee: 1.25, foot: -0.18, arm: -0.30, elbow: -0.35, torso: 0.03, head: 0 },
    sitback:{ hip: 0.59, thigh: -1.35, knee: 1.30, foot: -0.14, arm: -0.20, elbow: -0.30, torso: -0.12, head: -0.05 },
    coffee: { hip: 0.735, thigh: -1.30, knee: 1.25, foot: -0.18, arm: -0.95, elbow: -0.85, torso: 0.02, head: 0 },
    run:    { hip: 0.70, thigh: 0.02, knee: 0.02, foot: -0.04, arm: -1.05, elbow: -0.30, torso: 0.06, head: 0.04 }
  };

  /**
   * 加载角色模型（6 个 Quaternius 休闲风外观 + 两套坐姿重定向源）。
   * 全部失败才回退程序化小人；用 document.baseURI，站点可能挂在 /web/ 下。
   */
  function loadCharacter() {
    if (gltfPromise) return gltfPromise;
    const base = new URL('office/', document.baseURI).href;
    loadFaces(base);
    const loader = new GLTFLoader();
    const one = (u) => loader.loadAsync(u).catch((e) => {
      console.warn('[office] 角色资源加载失败：', u, e && (e.message || e));
      return null;
    });
    gltfPromise = Promise.all([
      ...CHAR_FILES.map((f) => one(base + CHAR_DIR + f)),
      one(base + CHAR_DIR + 'base-rig-animated.glb'),   // 素模：坐姿/蹦迪动作源
      one(base + 'agent.glb'),                         // 方块人：坐姿备用动作源
      one(base + SELF_FILE)                            // 自绘角色（首选外观）
    ]).then((all) => {
      const n = CHAR_FILES.length;
      charProtos = [];
      loadReport = [];
      all.slice(0, n).forEach((g, i) => {
        const file = CHAR_FILES[i];
        loadReport.push({ file, ok: !!g });
        if (!g) return;
        charProtos.push({
          file,
          scene: g.scene,
          animations: g.animations || [],
          scale: CHAR_SCALE[file] || 1,
          sitClip: undefined,
          sitRoute: ''
        });
      });
      const rigGltf = all[n];
      const agentGltf = all[n + 1];
      const rigProto = rigGltf ? { scene: rigGltf.scene, animations: rigGltf.animations || [] } : null;
      const agentProto = agentGltf ? { scene: agentGltf.scene, animations: agentGltf.animations || [] } : null;
      sitSources = {
        rig: rigProto && findClip(rigProto.animations, ['Sitting_Idle_Loop', 'Sitting_Enter'])
          ? { proto: rigProto, clip: findClip(rigProto.animations, ['Sitting_Idle_Loop', 'Sitting_Enter']), map: BONE_MAP_RIG }
          : null,
        agent: agentProto && findClip(agentProto.animations, ['sit'])
          ? { proto: agentProto, clip: findClip(agentProto.animations, ['sit']), map: BONE_MAP_AGENT }
          : null
      };
      /* 素模（CC-BY，需署名）里才有真正的 Dance / Talking 循环 */
      const rigClip = (cands) => (rigProto ? findClip(rigProto.animations, cands) : null);
      const danceClip = rigClip(['Dance_Loop', 'Dance', 'Cheer_Loop', 'Cheer']);
      danceSources = danceClip ? { proto: rigProto, clip: danceClip, map: BONE_MAP_RIG } : null;
      const talkClip = rigClip(['Idle_Talking_Loop', 'Talking_Loop', 'Standing_Talking', 'Talk']);
      singSources = talkClip ? { proto: rigProto, clip: talkClip, map: BONE_MAP_RIG } : null;

      /* 自绘角色：只有真拿到 5 条动作才启用，否则继续用 Quaternius */
      const selfGltf = all[n + 2];
      const selfClips = (selfGltf && selfGltf.animations) || [];
      const need = ['idle', 'walk', 'sit', 'dance', 'sing'];
      const hasAll = need.every((k) => selfClips.some((c) => clipShortName(c.name).toLowerCase() === k));
      loadReport.push({ file: SELF_FILE, ok: !!selfGltf, clips: selfClips.length, allActions: hasAll });
      selfProto = selfGltf && hasAll
        ? { file: SELF_FILE, scene: selfGltf.scene, animations: selfClips, scale: 1, own: true, sitClip: undefined, sitRoute: 'own' }
        : null;
      if (selfGltf && !hasAll) console.warn('[office] 自绘角色动作不全，用 Quaternius 外观：', selfClips.map((c) => c.name));

      useGltf = !!selfProto || charProtos.length > 0;
      if (!useGltf) console.warn('[office] 角色模型全部加载失败，回退程序化小人');
      return useGltf;
    });
    return gltfPromise;
  }

  /** 名字 hash → 外观下标（同一个 agent 每次进来都是同一套衣服） */
  function pickProto(name) {
    if (selfProto) return selfProto;          // 自绘角色优先
    if (!charProtos.length) return null;
    const s = String(name || 'agent');
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    const want = CHAR_FILES[h % CHAR_FILES.length];
    return charProtos.find((p) => p.file === want) || charProtos[h % charProtos.length];
  }

  /** 名字 hash → 衣服/发色/肤色；同一个人每次进来都是同一身 */
  function lookFor(name) {
    const s = String(name || 'agent');
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    const base = SELF_LOOKS[h % SELF_LOOKS.length];
    /* 发型跟性别对齐：0/1 男，2/3/4/5 女 */
    const styles = base.fem ? [2, 3, 4, 5, 6, 7, 8] : [0, 1];
    return {
      ...base,
      hairStyle: styles[(h >>> 4) % styles.length],
      hairColor: HAIR_COLORS[(h >>> 11) % HAIR_COLORS.length]
    };
  }

  /**
   * 座位家具有高有低：椅子坐垫 0.52、沙发 0.50、高脚凳 0.64。
   * 重定向出来的坐姿骨盆固定落在 0.52，坐高脚凳要整体抬一点、坐沙发压一点。
   */
  function sitLiftFor(seat) {
    if (!seat) return 0;
    const k = String(seat.key || '');
    if (seat.kind === 'coffee' || seat.kind === 'terrace') return 0.17;   // 高脚凳 0.64
    if (/^w\d+$/.test(k)) return 0.17;                                    // 2F 长条吧台也是高脚凳
    if (seat.kind === 'sofa') return 0.08;
    return 0.05;
  }

  /** 坐姿剪辑：优先素模 Sitting_Idle_Loop（真·循环坐姿），回退 agent.glb 的 sit 重定向 */
  function sitClipFor(proto) {
    if (proto.sitClip !== undefined) return proto.sitClip;
    let clip = null;
    let route = '';
    for (const [r, src] of [['rig', sitSources && sitSources.rig], ['agent', sitSources && sitSources.agent]]) {
      if (!src) continue;
      try {
        clip = retargetClip({ srcProto: src.proto, clip: src.clip, dstProto: proto, srcMap: src.map, name: 'sit' });
        if (clip && clip.tracks.length) { route = r; break; }
        clip = null;
      } catch (e) {
        console.warn('[office] 坐姿重定向失败（' + r + '）：', e && (e.message || e));
        clip = null;
      }
    }
    proto.sitClip = clip;
    proto.sitRoute = route;
    if (!clip) console.warn('[office] 没有可用的坐姿剪辑，改用「Idle + 压低」近似：', proto.file);
    return clip;
  }

  /**
   * 额外动作（dance / sing）：把素模的循环重定向到当前外观的骨骼上。
   * 失败返回 null，调用方回退到 Wave / Interact。
   */
  function extraClipFor(proto, kind) {
    const key = kind + 'Clip';
    if (proto[key] !== undefined) return proto[key];
    const src = kind === 'dance' ? danceSources : singSources;
    let clip = null;
    if (src) {
      try {
        clip = retargetClip({ srcProto: src.proto, clip: src.clip, dstProto: proto, srcMap: src.map, name: kind });
        if (clip && !clip.tracks.length) clip = null;
      } catch (e) {
        console.warn('[office] ' + kind + ' 重定向失败：', e && (e.message || e));
        clip = null;
      }
    }
    proto[key] = clip;
    return clip;
  }

  /** 从 glTF 原型上做一个"和 makePerson 同接口"的人 */
  function makeGltfPerson(name) {
    const proto = pickProto(name);
    if (!proto) return makePerson(name, false);

    /* 外层 root 只负责位置/朝向/缩放补间；模型自己再挂一层（女角色要缩 0.4，
       不能被 root.scale 的楼层过渡覆盖掉） */
    const root = new THREE.Group();
    const clone = _skeletonClone(proto.scene);
    clone.scale.setScalar(proto.scale);
    root.add(clone);
    scene.add(root);
    const own = !!proto.own;
    const look = own ? lookFor(name) : null;
    let faceMat = null;      // face_decal 的材质（换表情贴图用）
    /* 女角色身形略窄一圈（不改骨骼，只压模型 x/z；.945 够看出差别又不会显得畸形） */
    if (own && look.fem) clone.scale.set(0.945, 1, 0.95);
    const seenMat = new Set();
    clone.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      o.frustumCulled = false;
      if (own) {
        /* 三套发型都在 GLB 里，按人只留一套（其余节点隐藏，蒙皮照样存在但不渲染） */
        const hn = String(o.name || '');
        if (hn.indexOf('hair_') === 0) o.visible = hn.indexOf('hair_' + look.hairStyle) === 0;
        /* 裙子只有女角色穿 */
        if (hn.indexOf('skirt') === 0) o.visible = !!look.fem;
        /* 材质在克隆之间是共享的：换色必须先复制，否则一个人换色全楼跟着换 */
        o.material = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone();
        /* 注意：必须在 clone 之后再取 faceMat，否则拿到的是共享的原材质，换表情不生效 */
        if (hn.indexOf('face_decal') === 0) {
          faceMat = Array.isArray(o.material) ? o.material[0] : o.material;
        }
        const list = Array.isArray(o.material) ? o.material : [o.material];
        list.forEach((m) => {
          if (!m || seenMat.has(m)) return;
          seenMat.add(m);
          const nm = String(m.name || '').toLowerCase();
          const set = (rgb) => m.color && m.color.setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
          if (nm.includes('skin')) set(look.skin);
          else if (nm.includes('hair') || nm.includes('brow')) set(look.hairColor);
          else if (nm.includes('shirt')) set(look.shirt);
          else if (nm.includes('pants') || nm.includes('belt')) set(look.pants);
          else if (nm.includes('skirt')) set([0.34, 0.37, 0.48]);
          else if (nm.includes('shoe') || nm.includes('sole')) set([0.22, 0.20, 0.20]);
          else if (nm.includes('button') || nm.includes('white')) set([0.95, 0.95, 0.93]);
          if ('roughness' in m) m.roughness = 0.82;
          if ('metalness' in m) m.metalness = 0;
          /* 办公室只有平行光+半球光：深色（头发/深裤）会糊成纯黑，给一点同色自发光当轮廓提亮 */
          if ('emissive' in m && m.color && !nm.includes('face')) {
            const dark = nm.includes('hair') ? 0.30 : nm.includes('shoe') || nm.includes('sole') ? 0.12 : 0.05;
            m.emissive.copy(m.color).multiplyScalar(dark);
            if ('emissiveIntensity' in m) m.emissiveIntensity = 1;
          }
          /* 发片：单面薄片，要双面渲染 + alpha 裁剪；不投影（否则地上是方块影子） */
          if (nm.includes('haircard')) {
            /* 发片是灰度贴图 × 发色，比发帽暗，稍微提亮一点免得糊成黑 */
            set([Math.min(1, look.hairColor[0] * 1.45),
              Math.min(1, look.hairColor[1] * 1.45),
              Math.min(1, look.hairColor[2] * 1.45)]);
            m.side = THREE.DoubleSide;
            m.alphaTest = 0.32;
            m.transparent = false;
            o.castShadow = false;
          }
          if (nm.includes('face')) {
            m.transparent = true;
            m.depthWrite = false;
            m.polygonOffset = true;
            m.polygonOffsetFactor = -2;
            m.polygonOffsetUnits = -2;
          }
          m.needsUpdate = true;
        });
        return;
      }
      /* Quaternius 部分材质是 metalness=1 / roughness=1 且没有环境贴图，
         在只有平行光+半球光的场景里会渲染成**纯黑**。统一压成布料/皮肤的电介质材质。 */
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        if (!m) return;
        if ('metalness' in m) m.metalness = 0;
        if ('roughness' in m) m.roughness = 0.85;
        if ('envMapIntensity' in m) m.envMapIntensity = 0.6;
        m.side = THREE.FrontSide;

        /* 这套素材的 baseColorFactor 是线性空间；原包肤色偏深（woman 那套近乎深棕），
           统一改成东亚肤色 + 近黑发色（sRGB ≈ 0.93/0.80/0.69 → linear 0.85/0.60/0.44） */
        const nm = String(m.name || '').toLowerCase();
        if (m.color) {
          if (nm.includes('skin')) m.color.setRGB(0.85, 0.60, 0.44);
          else if (nm.includes('hair')) m.color.setRGB(0.016, 0.014, 0.013);
          else if (nm.includes('eyebrow') || nm === 'eye' || nm.includes('eyes')) m.color.setRGB(0.012, 0.010, 0.009);
        }
        /* 深色衣服在只有平行光的场景里容易糊成黑：给一点同色自发光当"轮廓提亮" */
        if ('emissive' in m) {
          m.emissive.copy(m.color).multiplyScalar(0.07);
          if ('emissiveIntensity' in m) m.emissiveIntensity = 1;
        }
        m.needsUpdate = true;
      });
      if (o.geometry && !o.geometry.attributes.normal) o.geometry.computeVertexNormals();
    });

    const mixer = new THREE.AnimationMixer(clone);
    const actions = {};   // 短名（去掉 CharacterArmature| 前缀，小写）
    proto.animations.forEach((c) => {
      const a = mixer.clipAction(c);
      a.setLoop(THREE.LoopRepeat, Infinity);
      actions[clipShortName(c.name).toLowerCase()] = a;
    });
    /* 名称模糊匹配（前缀不固定：CharacterArmature| / HumanArmature| / Rig|） */
    const resolve = (cands) => {
      for (const c of cands) {
        const k = c.toLowerCase();
        if (actions[k]) return actions[k];
      }
      for (const c of cands) {
        const k = c.toLowerCase();
        const hit = Object.keys(actions).find((n) => n.startsWith(k));
        if (hit) return actions[hit];
      }
      for (const c of cands) {
        const k = c.toLowerCase();
        const hit = Object.keys(actions).find((n) => n.includes(k));
        if (hit) return actions[hit];
      }
      return null;
    };
    const ACT = {
      idle: resolve(['Idle', 'Idle_Neutral', 'Female_Idle']),
      walk: resolve(['Walk', 'Female_Walk', 'Walk_Formal']),
      /* 包里没有 Dance：用 Wave 顶上并加快到 1.4 倍，看着像在晃 */
      dance: own ? resolve(['dance']) : resolve(['Wave', 'Interact', 'Female_Clapping', 'Dance']),
      stretch: own ? resolve(['stretch']) : null,
      sit_phone: own ? resolve(['sit_phone']) : null,
      sit_look: own ? resolve(['sit_look']) : null,
      phone: own ? resolve(['phone']) : null,
      look: own ? resolve(['look']) : null,
      /* 没有 Sing / Talk：用 Interact */
      sing: own ? resolve(['sing']) : resolve(['Interact', 'Female_Standing', 'Idle_Talking'])
    };
    /* 有真 Dance/Talking 就用真的，没有才退回 Wave / Interact（自绘角色自带，不用重定向） */
    if (!own) {
      const danceClip = extraClipFor(proto, 'dance');
      if (danceClip) {
        ACT.dance = mixer.clipAction(danceClip);
        ACT.dance.setLoop(THREE.LoopRepeat, Infinity);
      } else if (ACT.dance) {
        ACT.dance.timeScale = 1.4;
      }
      const singClip = extraClipFor(proto, 'sing');
      if (singClip) {
        ACT.sing = mixer.clipAction(singClip);
        ACT.sing.setLoop(THREE.LoopRepeat, Infinity);
      }
    }

    /* 坐姿（自绘角色用自己的 sit；其它外观走重定向，失败就 Idle + 压低） */
    let sitAction = null;
    const sitByKind = {};
    if (own) {
      sitByKind.chair = resolve(['sit']);
      sitByKind.sofa = resolve(['sit_sofa']) || sitByKind.chair;
      sitByKind.stool = resolve(['sit_stool']) || sitByKind.chair;
      sitAction = sitByKind.chair;
    } else {
      const sitClip = sitClipFor(proto);
      if (sitClip) {
        sitAction = mixer.clipAction(sitClip);
        sitAction.setLoop(THREE.LoopRepeat, Infinity);
      }
    }
    const SIT_DROP = 0.35;
    let seatLift = 0;

    let cur = null;
    const play = (a) => {
      if (!a || cur === a) return;
      a.reset().setEffectiveWeight(1).fadeIn(0.2).play();
      if (cur) cur.fadeOut(0.2);
      cur = a;
    };
    play(ACT.idle || ACT.walk);

    /* 话筒 / 杯子：挂到右手骨（Quaternius 是 Wrist.R；老模型是 Hand.R） */
    const findBone = (...names) => {
      for (const n of names) {
        const o = clone.getObjectByName(n);
        if (o) return o;
      }
      return null;
    };
    const hand = findBone('WristR', 'Wrist.R', 'HandR', 'Hand.R', 'hand.r', 'PalmR', 'Palm.R', 'DEF-handR');
    const headBone = findBone('Head');
    /* 脊柱：坐着玩电脑时前倾/后仰（打游戏前倾、看视频后仰） */
    const spineBone = findBone('Spine', 'Spine1', 'Chest');
    /* 前臂：坐着打字时抖两下（骨骼旋转必须放在 mixer.update 之后，否则会被动画覆盖） */
    const armL = findBone('LowerArmL', 'LowerArm.L', 'Forearm.L', 'lowerarm.l');
    const armR = findBone('LowerArmR', 'LowerArm.R', 'Forearm.R', 'lowerarm.r');
    /* 自绘角色的 Head 骨头在脖子处（y≈1.49），名牌/气泡要挂在头顶上方：
       额外挂一个空物体当锚点，headWorldPos 优先用它 */
    let headAnchor = null;
    if (own && headBone) {
      headAnchor = new THREE.Object3D();
      headAnchor.position.set(0, 0.27, 0);
      headBone.add(headAnchor);
    }
    /* 骨骼本身带着骨架根节点 100 倍缩放，道具挂上去会被放大 100 倍：
       先量一下手骨世界缩放，再把手里的东西缩回来（并保持"厘米级"局部坐标） */
    clone.updateMatrixWorld(true);
    const handWS = new THREE.Vector3(1, 1, 1);
    if (hand) hand.getWorldScale(handWS);
    const mount = new THREE.Group();
    if (hand) {
      mount.scale.setScalar(1 / (handWS.x || 1));
      hand.add(mount);
    }
    const mountOne = (geo, mat, pos, rot) => {
      const m = new THREE.Mesh(geo, mat);
      m.position.set(pos[0], pos[1], pos[2]);
      if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
      m.visible = false;
      m.castShadow = true;
      mount.add(m);
      return m;
    };
    const micMesh = mountOne(
      new THREE.CylinderGeometry(0.016, 0.02, 0.19, 10),
      new THREE.MeshStandardMaterial({ color: 0x2f333c, roughness: 0.5 }),
      [0, -0.1, 0.04],
      [0.5, 0, 0]
    );
    const micHead = mountOne(
      new THREE.SphereGeometry(0.042, 12, 10),
      new THREE.MeshStandardMaterial({ color: 0x9aa0aa, roughness: 0.3, metalness: 0.4 }),
      [0, -0.02, 0.10],
      null
    );
    const cupMesh = mountOne(
      new THREE.CylinderGeometry(0.036, 0.03, 0.075, 14),
      new THREE.MeshStandardMaterial({ color: 0xd8d4cc, roughness: 0.5 }),
      [0, -0.08, 0.05],
      [0.3, 0, 0]
    );

    /* 表情状态：眨眼（blink）优先于表情/说话，避免两处抢同一张贴图 */
    let faceMode = 'normal';
    let blinking = false;
    function applyFace() {
      if (!faceMat || !faceTex) return;
      const key = blinking ? 'blink' : (faceMode || 'normal');
      const tex = faceTex[key] || faceTex.normal;
      if (!tex || faceMat.map === tex) return;
      faceMat.map = tex;
      faceMat.needsUpdate = true;
    }

    return {
      root,
      hip: clone,            // 占位：tick 里的姿态写入对模型不生效（动作由 mixer 驱动）
      head: headBone || null, // 头是骨骼：名牌/气泡靠它定位，动作交给动画；不做额外转头
      headAnchor,
      mixer,
      charFile: proto.file,
      charName: own ? '自绘·' + look.name : (CHAR_NAME_CN[proto.file] || proto.file),
      sitRoute: proto.sitRoute,
      /** 座位家具高度不同（椅子/沙发/高脚凳），坐下时整体抬降一点 */
      setSeat(seat) {
        seatLift = sitLiftFor(seat);
        if (own && seat) {
          const k = seat.kind === 'sofa' ? 'sofa'
            : (seat.kind === 'coffee' || /^w\d+$/.test(String(seat.key || ''))) ? 'stool'
              : 'chair';
          if (sitByKind[k]) sitAction = sitByKind[k];
        }
      },
      /** 表情：换 face_decal 的贴图（normal/talk/happy/think/busy/tired/blink） */
      setMood(m) {
        const MAP = { idle: 'normal', busy: 'busy', wait: 'think', error: 'tired',
          happy: 'happy', talk: 'talk', think: 'think', tired: 'tired', normal: 'normal' };
        faceMode = MAP[m] || 'normal';
        if (blinking) return;      /* 眨眼那一帧别被表情覆盖 */
        applyFace();
      },
      /** 说话时的嘴型：在 normal / talk 之间来回切 */
      setTalking(on) {
        faceMode = on ? 'talk' : 'normal';
        if (blinking) return;
        applyFace();
      },
      /** 眨眼：换成闭眼贴图（face_blink.png），约 0.14 秒后恢复 */
      setBlink(on) {
        if (!faceMat || !faceTex || !faceTex.blink) return;
        if (on === blinking) return;
        blinking = !!on;
        applyFace();
      },
      setPose(p) {
        if (p === 'sit' || p === 'sit_phone' || p === 'sit_look') {
          const seatedAct = p === 'sit' ? sitAction : (ACT[p] || sitAction);
          if (seatedAct) {
            clone.position.y = seatLift;
            play(seatedAct);
          } else {
            /* 兜底：没有坐姿剪辑时用 Idle 并把模型整体压低 */
            clone.position.y = -SIT_DROP + seatLift;
            play(ACT.idle || ACT.walk);
          }
          return;
        }
        clone.position.y = 0;
        if (p === 'walk') play(ACT.walk || ACT.idle);
        else if (p === 'dance') play(ACT.dance || ACT.idle);
        else if (p === 'sing') play(ACT.sing || ACT.dance || ACT.idle);
        else if (p === 'stretch' && ACT.stretch) play(ACT.stretch);
        else if (p === 'phone' && ACT.phone) play(ACT.phone);
        else if (p === 'look' && ACT.look) play(ACT.look);
        else play(ACT.idle || ACT.walk);
      },
      /** 步频跟速度走：走慢时动画也慢下来，不然脚在"打滑"（像平移） */
      setSpeed(scale) {
        if (cur && cur.getClip) cur.timeScale = Math.max(0.55, Math.min(1.6, scale));
      },
      setProp(v) {
        const mic = v === 'mic';
        const cup = v === 'cup';
        micMesh.visible = mic;
        micHead.visible = mic;
        cupMesh.visible = cup;
      },
      /** 排查/验收用：当前脸贴图（眨眼时是 blink） */
      faceKey: () => (blinking ? 'blink' : (faceMode || 'normal')),
      state: () => ({}),
      cupPos: () => [0, 0, 0],
      /** 排查用：当前播放的动画名（dance / sit / idle …） */
      currentAction: () => (cur && cur.getClip ? cur.getClip().name : null),
      /* 模型角色的姿态/动作完全由 AnimationMixer 驱动（tickBody 里已经 update），
         这里必须留一个空实现：tickBody 会对每个 person 调 tick()，
         缺了它就会抛异常打断整帧（连 renderer.render 都跑不到 → 一个角色都看不见） */
      tick() {},
      /**
       * mixer.update 之后再补"人味"：扭头、说话点头、坐着打字。
       * 必须放在这里——主循环里改骨骼会被下一帧的 mixer.update 覆盖，
       * 这也是之前"坐着的人一动不动、说话也不动"的根因。
       */
      postUpdate(dt, t, st) {
        if (!st) return;
        const seed = st.seed || 0;
        /* 眨眼：每人周期错开（3.4~5.6 秒一次，闭 0.14 秒），换 face_blink 贴图 */
        if (faceTex && faceTex.blink) {
          const cyc = 3.4 + (seed % 3) * 1.1;
          const closed = ((t + seed * 1.7) % cyc) < 0.14;
          if (closed !== blinking) {
            blinking = closed;
            applyFace();
          }
        }
        if (headBone) {
          if (st.look) headBone.rotation.y += st.look;
          if (st.talking) {
            headBone.rotation.x += Math.sin(t * 6.2) * 0.05;
            headBone.rotation.z += Math.sin(t * 3.9) * 0.03;
          } else if (st.seated && !st.moving) {
            /* 坐着盯屏幕：呼吸点头 + 慢慢扫视 + 轻轻歪头（不是木头人） */
            headBone.rotation.x += Math.sin(t * 1.1 + seed) * 0.018;
            headBone.rotation.y += Math.sin(t * 0.31 + seed * 0.8) * 0.1;
            headBone.rotation.z += Math.sin(t * 0.19 + seed * 1.3) * 0.03;
            if (st.screen === 'video') headBone.rotation.x -= 0.05;
          }
        }
        if (st.seated && !st.moving && armL && armR) {
          if (st.desk) {
            const k = st.screen || 'work';
            if (k === 'game') {
              /* 打游戏：双手快速点按 + 前倾 */
              const g = Math.sin(t * 17) * 0.07 + Math.sin(t * 29 + 0.6) * 0.04;
              armL.rotation.x += g;
              armR.rotation.x += g * 1.15;
              if (spineBone) spineBone.rotation.x += 0.07 + Math.sin(t * 0.8) * 0.02;
            } else if (k === 'video') {
              /* 看视频：后仰、偶尔抬手 */
              if (spineBone) spineBone.rotation.x += -0.05 + Math.sin(t * 0.5) * 0.015;
              armR.rotation.x += Math.max(0, Math.sin(t * 1.3)) * 0.05;
            } else {
              /* 打字：两只前臂小幅快抖 */
              const kk = Math.sin(t * 11.5) * 0.05 + Math.sin(t * 7.7 + 0.8) * 0.03;
              armL.rotation.x += kk;
              armR.rotation.x += kk * 0.85;
            }
          } else if (st.talking) {
            /* 沙发/咖啡吧上说话：抬一下手当手势 */
            armR.rotation.x += Math.sin(t * 5.2) * 0.06;
          }
        }
      }
    };
  }

  function makePerson(name, lite) {
    /* 人物零件不打楼层标记：整组跟着 root 走，避免"人被拆散" */
    const prevFloorTag = buildingFloor;
    buildingFloor = undefined;
    const look = lookOf(name);
    const root = new THREE.Group();
    scene.add(root);
    const hip = new THREE.Group();
    hip.position.y = 0.9;
    root.add(hip);

    /* 骨盆 */
    B(0.255, 0.15, 0.185, look.pants, 0, -0.02, 0, 0.06, { parent: hip });
    /* 躯干：胶囊 + 上半身略宽 */
    const torso = mesh(new THREE.CapsuleGeometry(0.145, 0.13, 8, 18), look.shirt, 0, 0.215, 0, { parent: hip });
    torso.scale.set(1.06, 1.0, 0.74);
    /* 肩头 */
    [-1, 1].forEach(sd => {
      const sh = S(0.058, look.shirt, sd * 0.152, 0.355, 0, { parent: hip });
      sh.scale.set(1.0, 0.86, 0.86);
    });
    /* 衬衫领：两片小三角（不是纯圆柱脖子，近看有结构） */
    if (!lite) {
      [-1, 1].forEach(sd => {
        const col = B(0.062, 0.05, 0.022, look.collar, sd * 0.035, 0.392, 0.075, 0.008,
          { parent: hip, cast: false });
        col.rotation.z = sd * 0.5;
        col.rotation.x = -0.18;
      });
    }
    /* 腰带 */
    B(0.262, 0.028, 0.192, look.belt, 0, 0.045, 0, 0.012, { parent: hip, cast: false });
    /* 领口 + 脖子 */
    B(0.115, 0.026, 0.115, SKIN, 0, 0.412, 0, 0.012, { parent: hip, cast: false });
    C(0.042, 0.05, 0.075, SKIN, 0, 0.44, 0, 12, { parent: hip });
    /* 工牌 */
    if (!lite) {
      C(0.004, 0.004, 0.085, std('#8e97a4', { r: 0.6 }), 0.045, 0.36, 0.088, 6, { parent: hip, cast: false });
      B(0.05, 0.062, 0.008, std('#f7f9fc', { r: 0.5 }), 0.045, 0.315, 0.098, 0.008, { parent: hip, cast: false });
      B(0.03, 0.008, 0.004, std('#a9b6c8', { r: 0.6 }), 0.045, 0.30, 0.103, 0.003, { parent: hip, cast: false });
    }

    /* ===== 头 ===== */
    const headG = new THREE.Group();
    headG.position.set(0, 0.645, 0);
    hip.add(headG);

    const skull = mesh(new THREE.SphereGeometry(0.168, 30, 22), SKIN, 0, 0, 0, { parent: headG });
    skull.scale.set(1.0, 1.05, 0.96);

    /* 头发：顶部盖子 */
    const sty = look.style;
    const capT = (sty === 'short' || sty === 'side') ? Math.PI * 0.34 : Math.PI * 0.37;
    const cap = mesh(new THREE.SphereGeometry(0.172, 30, 22, 0, Math.PI * 2, 0, capT),
      look.hair, 0, 0.008, -0.006, { parent: headG });
    cap.scale.set(1.0, 1.04, 1.0);
    /* 后脑 */
    const back = mesh(new THREE.SphereGeometry(0.171, 26, 20, Math.PI * 1.14, Math.PI * 0.72, Math.PI * 0.22, Math.PI * 0.46),
      look.hair, 0, 0.01, -0.004, { parent: headG });
    back.scale.set(1.0, 1.02, 1.0);
    /* 刘海 / 变体 */
    if (sty === 'short') {
      const t = mesh(new THREE.SphereGeometry(0.075, 18, 14), look.hair, 0.02, 0.115, 0.085, { parent: headG });
      t.scale.set(1.5, 0.5, 0.85);
      t.rotation.z = 0.12;
    }
    if (sty === 'bowl' || sty === 'side') {
      const f = mesh(new THREE.SphereGeometry(0.098, 22, 16, 0, Math.PI * 2, 0, Math.PI * 0.5),
        look.hair, sty === 'side' ? 0.028 : 0, 0.105, 0.05, { parent: headG });
      f.scale.set(sty === 'side' ? 1.02 : 1.26, 0.42, 0.8);
      f.rotation.z = sty === 'side' ? 0.35 : 0;
    }
    if (sty === 'side') {
      const sweep = mesh(new THREE.SphereGeometry(0.10, 20, 14), look.hair, -0.05, 0.10, 0.042, { parent: headG });
      sweep.scale.set(0.85, 0.45, 0.9);
    }
    if (sty === 'bun') {
      const bun = S(0.062, look.hair, 0, 0.115, -0.13, { parent: headG });
      bun.scale.set(1.0, 0.85, 0.9);
    }
    if (sty === 'long') {
      const tail = mesh(new THREE.SphereGeometry(0.14, 22, 16), look.hair, 0, -0.045, -0.075, { parent: headG });
      tail.scale.set(0.95, 1.15, 0.72);
      const f2 = mesh(new THREE.SphereGeometry(0.10, 20, 14, 0, Math.PI * 2, 0, Math.PI * 0.52),
        look.hair, 0, 0.108, 0.048, { parent: headG });
      f2.scale.set(1.22, 0.4, 0.8);
    }

    /* 眼睛：竖椭圆 + 高光点 */
    [-1, 1].forEach(sd => {
      const e = mesh(new THREE.SphereGeometry(0.032, 14, 12), EYE, sd * 0.064, -0.004, 0.147,
        { parent: headG, cast: false });
      e.scale.set(0.82, 1.12, 0.5);
      const hl = mesh(new THREE.SphereGeometry(0.008, 8, 8), std('#ffffff', { r: 0.3 }),
        sd * 0.064 + 0.010, 0.008, 0.168, { parent: headG, cast: false });
      hl.scale.set(1, 1, 0.6);
    });
    /* 嘴：两套（微笑弧 / 张嘴），按状态切换 */
    const mouthSmile = mesh(new THREE.TorusGeometry(0.03, 0.0068, 8, 14, Math.PI), MOUTH,
      0, -0.05, 0.158, { parent: headG, cast: false });
    mouthSmile.rotation.z = Math.PI;
    mouthSmile.scale.set(1.0, 0.8, 0.6);
    const mouthOpen = mesh(new THREE.SphereGeometry(0.019, 12, 10), MOUTH,
      0, -0.055, 0.155, { parent: headG, cast: false });
    mouthOpen.scale.set(1.0, 1.15, 0.45);
    mouthOpen.visible = false;
    /* 眉毛 */
    const brows = [];
    if (!lite) [-1, 1].forEach(sd => {
      const b = B(0.042, 0.009, 0.012, look.hair, sd * 0.064, 0.042, 0.149, 0.003,
        { parent: headG, cast: false });
      b.rotation.z = sd * -0.08;
      brows.push(b);
    });
    /* 腮红（很淡） */
    if (!lite) [-1, 1].forEach(sd => {
      const c = mesh(new THREE.SphereGeometry(0.03, 12, 10), std('#f0b9a6', { r: 0.9, opacity: 0.5 }),
        sd * 0.104, -0.038, 0.126, { parent: headG, cast: false });
      c.scale.set(1.25, 0.75, 0.35);
      c.material.transparent = true;
    });
    /* 耳朵 */
    if (!lite) [-1, 1].forEach(sd => {
      const ear = mesh(new THREE.SphereGeometry(0.034, 12, 10), SKIN,
        sd * 0.163, -0.01, -0.012, { parent: headG, cast: false });
      ear.scale.set(0.55, 1.0, 0.85);
    });

    /* ===== 四肢 ===== */
    const legs = [], arms = [];
    [-1, 1].forEach(side => {
      const thigh = new THREE.Group();
      thigh.position.set(side * 0.088, -0.06, 0);
      hip.add(thigh);
      B(0.132, 0.34, 0.145, look.pants, 0, -0.17, 0, 0.055, { parent: thigh });

      const knee = new THREE.Group();
      knee.position.set(0, -0.34, 0);
      thigh.add(knee);
      B(0.118, 0.30, 0.128, look.pants, 0, -0.15, 0, 0.05, { parent: knee });

      /* 脚踝关节：让脚掌保持水平 */
      const ankle = new THREE.Group();
      ankle.position.set(0, -0.30, 0);
      knee.add(ankle);
      /* 鞋子：单个圆角整体（不再分「鞋面+鞋底」两块，走路不会脱层/散架） */
      B(0.12, 0.075, 0.23, look.shoe, 0, -0.033, 0.045, 0.032, { parent: ankle });
      legs.push({ thigh, knee, ankle });

      const arm = new THREE.Group();
      arm.position.set(side * 0.2, 0.35, 0);
      hip.add(arm);
      S(0.052, look.sleeve, 0, 0.006, 0, { parent: arm });
      B(0.105, 0.24, 0.105, look.sleeve, 0, -0.11, 0, 0.048, { parent: arm });

      const elbow = new THREE.Group();
      elbow.position.set(0, -0.225, 0);
      arm.add(elbow);
      B(0.088, 0.22, 0.088, SKIN, 0, -0.11, 0, 0.04, { parent: elbow });
      /* 手：哆啦A梦式圆球（不要手指，简单好看，也少点部件防穿模/散架） */
      S(0.062, SKIN, 0, -0.255, 0.004, { parent: elbow, cast: false });
      /* 右手：咖啡杯 / 手机（默认隐藏，按座位切换） */
      let cup = null, phone = null, mic = null;
      if (side === 1) {
        phone = new THREE.Group();
        const scr = mesh(new THREE.BoxGeometry(0.055, 0.1, 0.012), std('#2b3442', { r: 0.3 }),
          0, 0, 0, { parent: phone, cast: false });
        scr.rotation.x = -0.35;
        mesh(new THREE.BoxGeometry(0.045, 0.085, 0.004), std('#8fb4d8', { r: 0.4 }),
          0, 0.002, 0.008, { parent: phone, cast: false });
        phone.position.set(0.01, -0.3, 0.075);
        phone.rotation.x = 1.05;
        phone.visible = false;
        elbow.add(phone);
        cup = new THREE.Group();
        mesh(new THREE.CylinderGeometry(0.036, 0.030, 0.075, 16), std('#5f7185', { r: 0.45 }), 0, 0, 0, { parent: cup, cast: false });
        mesh(new THREE.CylinderGeometry(0.031, 0.031, 0.008, 16), std('#3f2f24', { r: 0.5 }), 0, 0.036, 0, { parent: cup, cast: false });
        const handle = mesh(new THREE.TorusGeometry(0.022, 0.007, 6, 10, Math.PI * 1.2), std('#5f7185', { r: 0.45 }), 0.036, 0.004, 0, { parent: cup, cast: false });
        handle.rotation.y = Math.PI / 2;
        /* 放在手掌前下方，别埋进手里 */
        cup.position.set(0.012, -0.345, 0.05);
        cup.rotation.x = 1.05;
        cup.visible = false;
        elbow.add(cup);

        /* 话筒：蹦迪时拿在手里唱 */
        mic = new THREE.Group();
        mesh(new THREE.CylinderGeometry(0.013, 0.017, 0.17, 10), std('#3b3f4a', { r: 0.45 }),
          0, 0, 0, { parent: mic, cast: false });
        mesh(new THREE.CylinderGeometry(0.038, 0.032, 0.022, 12), std('#5a5d66', { r: 0.4 }),
          0, 0.065, 0, { parent: mic, cast: false });
        mesh(new THREE.SphereGeometry(0.036, 12, 10), std('#9aa0aa', { r: 0.3 }),
          0, 0.098, 0, { parent: mic, cast: false });
        mic.position.set(0.01, -0.3, 0.07);
        mic.rotation.x = 1.3;
        mic.visible = false;
        elbow.add(mic);
      }
      arms.push({ arm, elbow, cup, phone, mic });
    });

    const cur = {
      hip: 0.90, thighL: 0.02, thighR: 0.02, kneeL: 0.02, kneeR: 0.02,
      footL: -0.04, footR: -0.04, armL: 0.06, armR: 0.06, elbow: -0.10, torso: 0, head: 0
    };
    let target = { ...POSES.stand };
    let mode = 'stand';

    const apply = () => {
      hip.position.y = cur.hip;
      legs[0].thigh.rotation.x = cur.thighL;
      legs[1].thigh.rotation.x = cur.thighR;
      legs[0].knee.rotation.x = cur.kneeL;
      legs[1].knee.rotation.x = cur.kneeR;
      legs[0].ankle.rotation.x = cur.footL;
      legs[1].ankle.rotation.x = cur.footR;
      arms[0].arm.rotation.x = cur.armL;
      arms[1].arm.rotation.x = cur.armR;
      arms[0].arm.rotation.z = 0.09;
      arms[1].arm.rotation.z = -0.09;
      arms[0].elbow.rotation.x = cur.elbow;
      arms[1].elbow.rotation.x = cur.elbow;
      hip.rotation.x = cur.torso;
      headG.rotation.x = cur.head;
    };

    const setProp = (v) => {
      arms.forEach(a => {
        if (a.cup) a.cup.visible = v === 'cup';
        if (a.phone) a.phone.visible = v === 'phone';
        if (a.mic) a.mic.visible = v === 'mic';
      });
    };

    const setMood = (mood) => {
      const open = mood === 'wait';
      mouthSmile.visible = !open;
      mouthOpen.visible = open;
      brows.forEach((b, i) => {
        const sd = i === 0 ? -1 : 1;
        b.rotation.z = mood === 'wait' ? sd * 0.28 : (mood === 'busy' ? sd * -0.16 : sd * -0.08);
        b.position.y = mood === 'wait' ? 0.05 : 0.042;
      });
    };

    buildingFloor = prevFloorTag;

    return {
      root, hip, head: headG, setMood, setProp,
      state: () => ({ ...cur, cup: arms.some(a => a.cup && a.cup.visible) }),
      cupPos: () => {
        let out = null;
        arms.forEach(a => { if (a.cup && a.cup.visible) { const v = new THREE.Vector3(); a.cup.getWorldPosition(v); out = [+v.x.toFixed(2), +v.y.toFixed(2), +v.z.toFixed(2)]; } });
        return out;
      },
      setPose(name) { mode = name; target = { ...(POSES[name] || POSES.stand) }; },
      tick(dt, t, moving) {
        if (mode === 'walk' || mode === 'run') {
          const sp = mode === 'run' ? 5.0 : 4.6;
          const amp = mode === 'run' ? 0.62 : 0.42;
          const kb = mode === 'run' ? 1.15 : 0.85;
          const ph = t * sp;

          [0, Math.PI].forEach((off, i) => {
            const p = ph + off;
            const th = amp * Math.sin(p);
            const kn = kb * (0.5 - 0.5 * Math.cos(p));
            const ft = -(th + kn) * 0.92;
            if (i === 0) { cur.thighL = th; cur.kneeL = kn; cur.footL = ft; }
            else { cur.thighR = th; cur.kneeR = kn; cur.footR = ft; }
          });

          /* 手里有东西就不摆那只手：端咖啡要稳，看手机要低头 */
          const holdCup = !!(arms[1].cup && arms[1].cup.visible);
          const holdPhone = !!(arms[1].phone && arms[1].phone.visible);
          const holding = holdCup || holdPhone;
          cur.armL = target.arm - 0.36 * Math.sin(ph);
          cur.armR = holding ? target.arm - 0.42 : target.arm + 0.36 * Math.sin(ph);
          cur.hip = target.hip - 0.012 * Math.abs(Math.sin(ph));
          cur.torso = target.torso + 0.04;
          cur.head = holdPhone ? 0.2 : target.head;
          cur.elbow = holding ? target.elbow - 0.5 : target.elbow - 0.12;
        } else {
          const k = Math.min(1, dt * 6.5);
          cur.hip += (target.hip - cur.hip) * k;
          cur.thighL += (target.thigh - cur.thighL) * k;
          cur.thighR += (target.thigh - cur.thighR) * k;
          cur.kneeL += (target.knee - cur.kneeL) * k;
          cur.kneeR += (target.knee - cur.kneeR) * k;
          cur.footL += (target.foot - cur.footL) * k;
          cur.footR += (target.foot - cur.footR) * k;
          cur.armL += (target.arm - cur.armL) * k;
          cur.armR += (target.arm - cur.armR) * k;
          cur.elbow += (target.elbow - cur.elbow) * k;
          cur.torso += (target.torso - cur.torso) * k;
          cur.head += (target.head - cur.head) * k;
        }
        apply();
      }
    };
  }

  /* 岗位：位置 + 姿势 + 朝向 */
  const SPOT = {
    front:   { p: [-3.9, 1.95], pose: 'stand', ry: 0 },
    dA:      { p: [-2.0, -1.75], pose: 'work', ry: Math.PI, ap: [0, 0.55] },
    dB:      { p: [0.7, -1.15], pose: 'work', ry: Math.PI, ap: [0, 0.55] },
    dC:      { p: [-3.1, 0.05], pose: 'work', ry: Math.PI, ap: [0, 0.55] },
    dD:      { p: [-0.4, 0.65], pose: 'work', ry: Math.PI, ap: [0, 0.55] },
    qc:      { p: [4.8, -2.4], pose: 'work', ry: Math.PI, ap: [0, 0.55] },
    qc2:     { p: [4.8, -3.82], pose: 'work', ry: 0, ap: [0, 0.55] },
    coffee1: { p: [3.5, 2.95], pose: 'coffee', ry: Math.PI, ap: [0, 0.55], cup: true },
    coffee2: { p: [4.7, 2.95], pose: 'coffee', ry: Math.PI, ap: [0, 0.55], cup: true },
    sofa1:   { p: [-1.1, 3.5], pose: 'sitback', ry: Math.PI, ap: [0, -0.62] },
    sofa2:   { p: [0.35, 3.5], pose: 'sitback', ry: Math.PI, ap: [0, -0.62] },
    gym:     { p: [-5.5, -3.25], pose: 'run', ry: Math.PI, ap: [0.75, 0] },
    door:    { p: [-5.3, 3.85], pose: 'stand', ry: Math.PI },
    aisle:   { p: [2.4, 0.9], pose: 'stand', ry: 0 }
  };

  /* ================= 导航网格（障碍物 + A*） ================= */
  const OBSTACLES = [];
  const OBSTACLES2 = [];   // 二层自己的家具
  const addObst = (x1, z1, x2, z2) => OBSTACLES.push([
    Math.min(x1, x2), Math.min(z1, z2), Math.max(x1, x2), Math.max(z1, z2)
  ]);

  /* 工位：桌面 + 抽屉柜 + 椅子整块 */
  DESKS.forEach(d => addObst(d.x - 0.8, d.z - 0.42, d.x + 0.8, d.z + 0.98));
  /* 前台 */
  addObst(-5.2, 2.3, -2.58, 3.12);
  /* 玻璃房四壁（南面留门洞 4.72~5.78） */
  addObst(3.22, -4.6, 6.38, -4.52);
  addObst(3.22, -4.6, 3.3, -1.52);
  addObst(6.3, -4.6, 6.38, -1.52);
  addObst(3.22, -1.72, 4.72, -1.62);
  addObst(5.78, -1.72, 6.38, -1.62);
  addObst(4.2, -3.5, 5.42, -2.72);
  /* 咖啡吧（吧台 + 转角） */
  addObst(2.66, 1.6, 5.74, 2.4);
  addObst(5.42, 0.48, 6.16, 2.08);
  [[3.5, 2.95], [4.7, 2.95], [5.85, 2.62]].forEach(([x, z]) => addObst(x - 0.22, z - 0.22, x + 0.22, z + 0.22));
  /* 健身角 */
  addObst(-5.98, -4.3, -5.02, -2.4);
  addObst(-4.22, -4.32, -2.88, -3.9);
  /* 休息区 */
  addObst(-1.74, 3.03, 0.94, 4.06);
  addObst(1.48, 3.08, 2.42, 4.02);
  addObst(-2.82, 3.08, -2.38, 3.52);
  /* 落地绿植 */
  addObst(2.8, 0.8, 3.3, 1.3);
  addObst(6.3, -1.4, 6.8, -0.9);
  /* 书柜 */
  addObst(-6.42, -1.38, -6.04, 0.58);
  /* 卫生间（南面留门洞 -6.46~-5.84） */
  addObst(-6.8, 1.72, -6.66, 3.68);
  addObst(-6.8, 1.7, -5.2, 1.82);
  addObst(-5.34, 1.72, -5.2, 3.68);
  addObst(-6.8, 3.58, -6.46, 3.68);
  addObst(-5.84, 3.58, -5.2, 3.68);
  addObst(-6.42, 1.95, -6.1, 2.55);
  addObst(-5.85, 1.95, -5.5, 2.45);

  const makeNav = (OBST) => {
    const CELL = 0.15, X0 = -6.9, Z0 = -4.9;
    const COLS = 92, ROWS = 96;   // 往 +z 多留一段给露台
    const blocked = new Uint8Array(COLS * ROWS);
    const at = (c, r) => r * COLS + c;
    const toCell = (x, z) => [Math.round((x - X0) / CELL), Math.round((z - Z0) / CELL)];
    const toWorld = (c, r) => [X0 + c * CELL, Z0 + r * CELL];
    /* 人体半宽约 0.16m，加上走路时腿脚前后摆动、起身时身体前后倾，
       路径若贴家具边 0.2m，腿脚会视觉插进桌椅。加大到 0.28 让身体整体避开，
       实测仍能连通所有工位/关键点（RAD=0.3 会堵死过道，故取 0.28）。 */
    const RAD = 0.28;

    /* 按格子中心判定，避免 ceil 多占一圈 */
    OBST.forEach(([x1, z1, x2, z2]) => {
      const c0 = Math.floor((x1 - RAD - X0) / CELL), c1 = Math.ceil((x2 + RAD - X0) / CELL);
      const r0 = Math.floor((z1 - RAD - Z0) / CELL), r1 = Math.ceil((z2 + RAD - Z0) / CELL);
      for (let r = Math.max(0, r0); r <= Math.min(ROWS - 1, r1); r++) {
        for (let c = Math.max(0, c0); c <= Math.min(COLS - 1, c1); c++) {
          const cx = X0 + c * CELL, cz = Z0 + r * CELL;
          if (cx > x1 - RAD && cx < x2 + RAD && cz > z1 - RAD && cz < z2 + RAD) blocked[at(c, r)] = 1;
        }
      }
    });
    /* 外圈当墙 */
    for (let c = 0; c < COLS; c++) { blocked[at(c, 0)] = 1; blocked[at(c, ROWS - 1)] = 1; }
    for (let r = 0; r < ROWS; r++) { blocked[at(0, r)] = 1; blocked[at(COLS - 1, r)] = 1; }

    const free = (c, r) => c >= 0 && r >= 0 && c < COLS && r < ROWS && !blocked[at(c, r)];

    /* 座位挖口：沿"出场方向"清一条走廊，保证能走到座位上 */
    const carve = (x, z, ax, az) => {
      const [c0, r0] = toCell(x, z);
      const [c1, r1] = toCell(x + ax, z + az);
      const steps = Math.max(Math.abs(c1 - c0), Math.abs(r1 - r0), 1);
      for (let i = 0; i <= steps; i++) {
        const c = Math.round(c0 + (c1 - c0) * i / steps);
        const r = Math.round(r0 + (r1 - r0) * i / steps);
        if (c > 0 && r > 0 && c < COLS - 1 && r < ROWS - 1) blocked[at(c, r)] = 0;
      }
    };
    Object.values(SPOT).forEach(s2 => { if (s2.ap) carve(s2.p[0], s2.p[1], s2.ap[0], s2.ap[1]); });

    function nearestFree(c, r) {
      if (free(c, r)) return [c, r];
      for (let rad = 1; rad <= 14; rad++) {
        for (let dr = -rad; dr <= rad; dr++) {
          for (let dc = -rad; dc <= rad; dc++) {
            if (Math.max(Math.abs(dc), Math.abs(dr)) !== rad) continue;
            if (free(c + dc, r + dr)) return [c + dc, r + dr];
          }
        }
      }
      return null;
    }

    function lineFree(x1, z1, x2, z2) {
      const d = Math.hypot(x2 - x1, z2 - z1);
      const n = Math.max(2, Math.ceil(d / 0.08));
      for (let i = 0; i <= n; i++) {
        const t = i / n;
        const [c, r] = toCell(x1 + (x2 - x1) * t, z1 + (z2 - z1) * t);
        if (!free(c, r)) return false;
      }
      return true;
    }

    function astar(sc, sr, tc, tr) {
      const N = COLS * ROWS;
      const g = new Float32Array(N).fill(Infinity);
      const f = new Float32Array(N).fill(Infinity);
      const prev = new Int32Array(N).fill(-1);
      const open = [at(sc, sr)];
      const inOpen = new Uint8Array(N);
      const closed = new Uint8Array(N);
      g[at(sc, sr)] = 0;
      f[at(sc, sr)] = Math.hypot(tc - sc, tr - sr);
      inOpen[at(sc, sr)] = 1;

      const DIRS = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
                    [1, 1, 1.4142], [1, -1, 1.4142], [-1, 1, 1.4142], [-1, -1, 1.4142]];

      while (open.length) {
        let bi = 0;
        for (let i = 1; i < open.length; i++) if (f[open[i]] < f[open[bi]]) bi = i;
        const cur = open.splice(bi, 1)[0];
        inOpen[cur] = 0;
        if (cur === at(tc, tr)) break;
        closed[cur] = 1;
        const cc = cur % COLS, cr = (cur - cc) / COLS;

        for (const [dc, dr, cost] of DIRS) {
          const nc = cc + dc, nr = cr + dr;
          if (!free(nc, nr)) continue;
          if (dc && dr && (!free(cc + dc, cr) || !free(cc, cr + dr))) continue;
          const ni = at(nc, nr);
          if (closed[ni]) continue;
          const ng = g[cur] + cost;
          if (ng < g[ni]) {
            g[ni] = ng;
            f[ni] = ng + Math.hypot(tc - nc, tr - nr);
            prev[ni] = cur;
            if (!inOpen[ni]) { open.push(ni); inOpen[ni] = 1; }
          }
        }
      }

      if (prev[at(tc, tr)] === -1 && !(sc === tc && sr === tr)) return null;
      const cells = [];
      let cur = at(tc, tr);
      while (cur !== -1) {
        const c = cur % COLS, r = (cur - c) / COLS;
        cells.push([c, r]);
        if (c === sc && r === sr) break;
        cur = prev[cur];
      }
      cells.reverse();
      return cells.map(([c, r]) => toWorld(c, r));
    }

    function findPath(sx, sz, tx, tz) {
      let [sc, sr] = toCell(sx, sz);
      let [tc, tr] = toCell(tx, tz);
      if (!free(sc, sr)) { const n = nearestFree(sc, sr); if (!n) return null; [sc, sr] = n; }
      if (!free(tc, tr)) { const n = nearestFree(tc, tr); if (!n) return null; [tc, tr] = n; }
      const raw = astar(sc, sr, tc, tr);
      if (!raw) return null;
      /* 拉直：能直达就跳过中间点 */
      const out = [];
      let i = 0;
      while (i < raw.length - 1) {
        let j = raw.length - 1;
        while (j > i + 1 && !lineFree(raw[i][0], raw[i][1], raw[j][0], raw[j][1])) j--;
        out.push(raw[j]);
        i = j;
      }
      if (!out.length) out.push(raw[raw.length - 1]);
      return out;
    }

    return { findPath, free, toCell, toWorld, carve };
  };

  /* ================= 楼梯口（点它上下楼） ================= */
  const STAIR = { x: -6.0, z: 3.95 };

  function buildStair(floor) {
    const up = floor === 1;
    buildingFloor = floor;
    buildingY = floor === 2 ? FLOOR_H : 0;
    /* 3 级台阶（视觉暗示）+ 平台 */
    for (let i = 0; i < 3; i++) {
      B(1.15 - i * 0.06, 0.16, 0.34, M.deskEdge, STAIR.x, 0.08 + i * 0.16, STAIR.z - i * 0.34, 0.01,
        { cast: false });
    }
    B(1.2, 0.06, 1.2, M.slab, STAIR.x, 0.02, STAIR.z, 0.01, { cast: false });
    /* 立牌：每层自己一张 canvas（共用一个会被后画的覆盖） */
    const signCv = document.createElement('canvas');
    signCv.width = 256;
    signCv.height = 128;
    const sctx = signCv.getContext('2d');
    sctx.fillStyle = 'rgba(10,18,30,0.9)';
    sctx.fillRect(0, 0, 256, 128);
    sctx.strokeStyle = '#5ec8ff';
    sctx.lineWidth = 4;
    sctx.strokeRect(3, 3, 250, 122);
    sctx.fillStyle = '#5ec8ff';
    sctx.font = 'bold 60px "Microsoft YaHei", sans-serif';
    sctx.textAlign = 'center';
    sctx.textBaseline = 'middle';
    sctx.fillText(up ? '2F ↑' : '1F ↓', 128, 54);
    sctx.fillStyle = '#8ba0b8';
    sctx.font = '22px "Microsoft YaHei", sans-serif';
    sctx.fillText(up ? 'STAIRS UP' : 'STAIRS DOWN', 128, 98);
    const signTex = new THREE.CanvasTexture(signCv);
    signTex.colorSpace = THREE.SRGBColorSpace;
    signTex.needsUpdate = true;

    const post = new THREE.Group();
    post.position.set(STAIR.x + 0.78, floor === 2 ? FLOOR_H : 0, STAIR.z - 0.05);
    post.userData.floor = floor;
    scene.add(post);

    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 1.2, 8), M.metal);
    pole.position.y = 0.6;
    pole.userData.floor = floor;
    post.add(pole);

    /* 牌子用 Sprite：永远正面朝镜头，不受朝向/背面剔除影响 */
    const sign = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: signTex, transparent: true, depthWrite: false })
    );
    sign.name = 'stair-sign-' + floor;
    sign.scale.set(0.66, 0.33, 1);
    sign.position.set(0, 1.34, 0);
    sign.userData.floor = floor;
    sign.renderOrder = 8;
    post.add(sign);
    buildingFloor = 1;
    buildingY = 0;
  }

  /* ================= 二层（夹层）：和一层不一样的布局 ================= */
  /** 舞池站位（不放进 SEAT_DEF，避免被普通排座算法占走） */
  const DANCE_SPOTS = [];
  function buildDanceSpots(cx, cz) {
    const ring = [
      [-1.55, -0.62], [-0.55, -0.72], [0.55, -0.72], [1.55, -0.62],
      [-1.55, 0.62], [1.55, 0.62]
    ];
    ring.forEach(([dx, dz], i) => {
      DANCE_SPOTS.push({
        key: 'dance' + (i + 1),
        kind: 'dance',
        floor: 2,
        p: [cx + dx, cz + dz],
        ry: Math.atan2(cx - (cx + dx), cz - (cz + dz)), // 面朝舞池中心
        pose: 'stand'
      });
    });
  }
  let discoRig = null;      // 旋转彩灯组
  let discoBall = null;     // 反光彩球
  let discoCones = [];      // 四束彩色光锥（跟节拍脉动）
  let discoGlow = null;     // 地面柔光
  let discoNeon = null;     // PARTY 霓虹牌
  let discoLightRef = null; // 彩色点光
  let discoPower = 0;       // 0=关着（没人），1=全开；进出时淡入淡出
  /* 一层是 4 张散落工位 + 会客室 + 咖啡吧；二层是"项目区"：两排 6 个工位 + 小会议角 */
  const F2_DESKS = [
    { x: -3.6, z: -2.6 }, { x: -1.2, z: -2.6 }, { x: 1.2, z: -2.6 },
    { x: -3.6, z: 0.4 }, { x: -1.2, z: 0.4 }, { x: 1.2, z: 0.4 }
  ];
  const F2_MEET = { x: 4.7, z: 0.2 };   // 小会议桌
  const F2_BENCH = [-2.4, -0.8, 0.8, 2.4];   // 窗边长桌的 4 个位子

  buildingFloor = 2;
  buildingY = FLOOR_H;
  {
    /* 楼板 + 地材 */
    B(FW + 0.5, 0.18, FD + 0.5, M.slab, 0, -0.09, 0, 0.03, { cast: false });
    B(FW, 0.06, FD, M.floor2, 0, 0, 0, 0.02, { cast: false });
    /* 矮墙（保持夹层通透） */
    B(FW + 0.2, 1.2, 0.12, M.wall2, 0, 0.6, -FD / 2 + 0.06, 0.02);
    B(0.12, 1.2, FD + 0.2, M.wall2, -FW / 2 + 0.06, 0.6, 0, 0.02);

    /* 两排工位（布局与一层不同） */
    F2_DESKS.forEach(desk);
    F2_DESKS.forEach(d => {
      OBSTACLES2.push([d.x - 0.8, d.z - 0.42, d.x + 0.8, d.z + 0.98]);
    });

    /* 窗边长桌：靠北墙一排，4 个高脚位（对着窗户办公） */
    B(5.4, 0.06, 0.66, M.wood, 0, 0.74, -4.02, 0.02);
    B(5.2, 0.02, 0.6, M.deskEdge, 0, 0.775, -4.02, 0.01, { cast: false });
    [-2.55, -0.85, 0.85, 2.55].forEach(x => {
      C(0.04, 0.04, 0.72, M.metal, x, 0.37, -4.02, 8, { cast: false });
      /* 桌上一台笔记本 */
      B(0.34, 0.02, 0.24, M.laptop, x, 0.79, -4.06, 0.008, { cast: false });
      B(0.32, 0.2, 0.02, M.screen, x, 0.9, -4.16, 0.006, { rx: -0.3, cast: false });
    });
    F2_BENCH.forEach(x => stool(x, -3.46, 0.64));
    OBSTACLES2.push([-2.8, -4.42, 2.8, -3.68]);

    /* 小会议角：圆桌 + 两把椅子 */
    C(0.62, 0.62, 0.05, M.wood, F2_MEET.x, 0.74, F2_MEET.z, 28, { cast: false });
    C(0.06, 0.06, 0.72, M.metal, F2_MEET.x, 0.37, F2_MEET.z, 8, { cast: false });
    C(0.3, 0.3, 0.03, M.metal, F2_MEET.x, 0.03, F2_MEET.z, 18, { cast: false });
    /* 椅子默认面朝 -z；南侧那把要朝北（ry=PI），北侧那把朝南（ry=0） */
    chair(F2_MEET.x, F2_MEET.z - 0.95, Math.PI);
    chair(F2_MEET.x, F2_MEET.z + 0.95, 0);
    OBSTACLES2.push([F2_MEET.x - 0.68, F2_MEET.z - 0.68, F2_MEET.x + 0.68, F2_MEET.z + 0.68]);

    /* 茶水角：台面 + 咖啡机 + 两个高脚位 */
    B(1.9, 0.9, 0.62, M.desk, 5.35, 0.45, 2.55, 0.02);
    B(1.98, 0.05, 0.7, M.wood, 5.35, 0.92, 2.55, 0.02);
    B(0.34, 0.34, 0.3, M.desk, 5.55, 1.12, 2.45, 0.02, { cast: false });
    B(0.36, 0.05, 0.32, M.darkMetal, 5.55, 1.31, 2.45, 0.01, { cast: false });
    C(0.04, 0.04, 0.06, M.darkMetal, 5.55, 1.25, 2.6, 10, { cast: false });
    [4.95, 5.75].forEach(x => stool(x, 3.15, 0.64));
    OBSTACLES2.push([4.38, 2.2, 6.32, 2.9]);

    /* 白板（和一层同款，但挂在二层北墙） */
    B(1.5, 0.94, 0.04, M.paper, -1.6, 1.12, -FD / 2 + 0.14, 0.01, { cast: false });
    B(1.52, 0.05, 0.05, M.metal, -1.6, 1.6, -FD / 2 + 0.15, 0.01, { cast: false });
    for (let i = 0; i < 3; i++) {
      B(0.8 - i * 0.16, 0.014, 0.006, M.dark, -1.75 + (i % 2) * 0.2, 1.42 - i * 0.15,
        -FD / 2 + 0.17, 0.002, { cast: false });
    }
    /* 二层也投一块"最近结论"屏（和一层白板共用同一张 canvas，改一处两边都变） */
    const board2 = new THREE.Mesh(
      new THREE.PlaneGeometry(1.7, 1.02),
      new THREE.MeshBasicMaterial({ map: BOARD_TEX, toneMapped: false })
    );
    board2.position.set(1.9, FLOOR_H + 1.16, -FD / 2 + 0.17);
    board2.userData.floor = 2;
    scene.add(board2);
    B(1.78, 1.1, 0.05, M.metal, 1.9, 1.16, -FD / 2 + 0.13, 0.01, { cast: false });

    /* ===== 玻璃舞厅：玻璃隔断 + 舞池 + 彩球 + 旋转彩灯 + 话筒 ===== */
    const DISCO = { x: 1.6, z: 3.0 };
    const DR_W = 5.0;   // 玻璃房宽（x）
    const DR_D = 2.9;   // 玻璃房深（z）
    const dcv = document.createElement('canvas');
    dcv.width = 320;
    dcv.height = 208;
    const dctx = dcv.getContext('2d');
    for (let gy = 0; gy < 8; gy++) {
      for (let gx = 0; gx < 12; gx++) {
        dctx.fillStyle = (gx + gy) % 2 ? '#5a4f7a' : '#6a5c92';
        dctx.fillRect(gx * 26.6, gy * 26, 26.6, 26);
        if ((gx * 7 + gy * 5) % 11 === 0) {
          dctx.fillStyle = ['#ff8ec4', '#8fd6ff', '#ffe08a'][(gx + gy) % 3];
          dctx.fillRect(gx * 26.6 + 8, gy * 26 + 8, 11, 11);
        }
      }
    }
    dctx.strokeStyle = '#ff5ea8';
    dctx.lineWidth = 10;
    dctx.strokeRect(5, 5, 310, 198);
    dctx.strokeStyle = '#5ec8ff';
    dctx.lineWidth = 3;
    dctx.strokeRect(17, 17, 286, 174);
    const dtex = new THREE.CanvasTexture(dcv);
    dtex.colorSpace = THREE.SRGBColorSpace;
    const danceFloor = new THREE.Mesh(
      new THREE.PlaneGeometry(4.6, 2.5),
      new THREE.MeshBasicMaterial({ map: dtex })
    );
    danceFloor.rotation.x = -Math.PI / 2;
    danceFloor.position.set(DISCO.x, FLOOR_H + 0.04, DISCO.z);
    danceFloor.userData.floor = 2;
    scene.add(danceFloor);

    /* 地面柔光 */
    const glowCv = document.createElement('canvas');
    glowCv.width = 128;
    glowCv.height = 128;
    const gctx = glowCv.getContext('2d');
    const grad = gctx.createRadialGradient(64, 64, 6, 64, 64, 62);
    grad.addColorStop(0, 'rgba(255,150,210,0.55)');
    grad.addColorStop(0.55, 'rgba(120,190,255,0.22)');
    grad.addColorStop(1, 'rgba(120,190,255,0)');
    gctx.fillStyle = grad;
    gctx.fillRect(0, 0, 128, 128);
    const glowTex = new THREE.CanvasTexture(glowCv);
    const glowPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(4.8, 2.7),
      new THREE.MeshBasicMaterial({
        map: glowTex, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, opacity: 0.85
      })
    );
    glowPlane.rotation.x = -Math.PI / 2;
    glowPlane.position.set(DISCO.x, FLOOR_H + 0.05, DISCO.z);
    glowPlane.userData.floor = 2;
    scene.add(glowPlane);
    discoGlow = glowPlane;

    /* 彩球（挂在顶部灯架下面，不悬空） */
    discoBall = new THREE.Mesh(
      new THREE.SphereGeometry(0.23, 26, 18),
      new THREE.MeshStandardMaterial({
        color: 0xe6ecf6, metalness: 0.98, roughness: 0.12,
        emissive: 0x8fa6c8, emissiveIntensity: 0.55
      })
    );
    discoBall.position.set(DISCO.x, FLOOR_H + 2.0, DISCO.z);
    discoBall.userData.floor = 2;
    scene.add(discoBall);

    /* 四束彩色光锥 */
    discoRig = new THREE.Group();
    discoRig.position.set(DISCO.x, FLOOR_H + 2.0, DISCO.z);
    for (let i = 0; i < 4; i++) {
      const col = [0xff5ea8, 0x5ec8ff, 0xffd166, 0x8affc1][i];
      const cone = new THREE.Mesh(
        new THREE.ConeGeometry(0.52, 1.9, 20, 1, true),
        new THREE.MeshBasicMaterial({
          color: col, transparent: true, opacity: 0.2,
          side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending
        })
      );
      cone.position.set(Math.cos((i * Math.PI) / 2) * 0.42, -0.95, Math.sin((i * Math.PI) / 2) * 0.42);
      cone.rotation.z = Math.cos((i * Math.PI) / 2) * 0.3;
      cone.rotation.x = -Math.sin((i * Math.PI) / 2) * 0.3;
      cone.userData.floor = 2;
      discoRig.add(cone);
      discoCones.push(cone);
    }
    discoRig.userData.floor = 2;
    scene.add(discoRig);

    /* 距离 5.4 会一路照到一楼地面（y=0.05）——收到 2.4，配合 layer 只照二层 */
    const discoLight = new THREE.PointLight(0xff5ea8, 3.4, 2.8, 2);
    discoLight.position.set(DISCO.x, FLOOR_H + 1.9, DISCO.z);
    discoLight.userData.floor = 2;
    scene.add(discoLight);
    discoLight.layers.set(2);   // 只影响 layer 2（二层物体）
    discoLightRef = discoLight;

    /* 玻璃隔断：北/东/南 三面整墙，西面留门（宽 1.0） */
    const GH2 = 2.15;
    const doorW = 0.95;
    const sideW = (DR_D - doorW) / 2;
    const danceWalls = [
      glassRun(DR_W, DISCO.x, DISCO.z - DR_D / 2, 0),            // 北
      glassRun(DR_W, DISCO.x, DISCO.z + DR_D / 2, 0),            // 南
      glassRun(DR_D, DISCO.x + DR_W / 2, DISCO.z, Math.PI / 2),  // 东
      glassRun(sideW, DISCO.x - DR_W / 2, DISCO.z - (doorW + sideW) / 2, Math.PI / 2),
      glassRun(sideW, DISCO.x - DR_W / 2, DISCO.z + (doorW + sideW) / 2, Math.PI / 2)
    ];
    /* glassRun 里的玻璃面用的是 raw mesh（没走 B()），不会自动加楼层高度，
       二层会把玻璃板留在 1F 高度 —— 这里补回来 */
    danceWalls.forEach(g => {
      g.children.forEach(o => {
        if (o.material === M.glass) o.position.y += FLOOR_H;
      });
    });

    /* ===== 顶部灯架：舞厅是开顶的等距视角，灯必须有"挂在架子上"的落点 ===== */
    const TR_Y = GH2 + 0.46;
    const postH = TR_Y - GH2;
    /* 四角立柱（从玻璃墙顶伸到灯架） */
    [-1, 1].forEach(sx => {
      [-1, 1].forEach(sz => {
        C(0.025, 0.025, postH, M.frame,
          DISCO.x + sx * (DR_W / 2), GH2 + postH / 2, DISCO.z + sz * (DR_D / 2), 8,
          { cast: false });
      });
    });
    /* 四面横梁 + 中间承重横梁 */
    /* 和玻璃框同粗（0.05）同材质，远看是一套结构，不像两套框叠着 */
    B(DR_W, 0.05, 0.05, M.frame, DISCO.x, TR_Y, DISCO.z - DR_D / 2, 0.008, { cast: false });
    B(DR_W, 0.05, 0.05, M.frame, DISCO.x, TR_Y, DISCO.z + DR_D / 2, 0.008, { cast: false });
    B(0.05, 0.05, DR_D, M.frame, DISCO.x - DR_W / 2, TR_Y, DISCO.z, 0.008, { cast: false });
    B(0.05, 0.05, DR_D, M.frame, DISCO.x + DR_W / 2, TR_Y, DISCO.z, 0.008, { cast: false });
    B(DR_W, 0.045, 0.045, M.frame, DISCO.x, TR_Y, DISCO.z, 0.006, { cast: false });
    /* 吊杆：灯架中点 → 彩球顶 */
    const rodTop = TR_Y;
    const rodBottom = 2.0 + 0.23;
    C(0.022, 0.022, rodTop - rodBottom, M.frame,
      DISCO.x, (rodTop + rodBottom) / 2, DISCO.z, 8, { cast: false });
    C(0.065, 0.065, 0.04, M.frame, DISCO.x, rodTop - 0.03, DISCO.z, 14, { cast: false });
    /* 灯架上的两只小灯壳（让光看着是从灯架下来的） */
    [-0.85, 0.85].forEach(dx => {
      C(0.1, 0.12, 0.16, M.darkMetal, DISCO.x + dx, TR_Y - 0.1, DISCO.z, 14, { cast: false });
      C(0.055, 0.075, 0.05, M.glassEdge, DISCO.x + dx, TR_Y - 0.2, DISCO.z, 14, { cast: false });
    });

    /* 门楣霓虹 + PARTY 牌（在门上方） */
    B(DR_W, 0.05, 0.06, M.glassEdge, DISCO.x, GH2 + 0.02, DISCO.z - DR_D / 2, 0.004, { cast: false });
    const neonCv = document.createElement('canvas');
    neonCv.width = 256;
    neonCv.height = 96;
    const nctx = neonCv.getContext('2d');
    nctx.fillStyle = 'rgba(12,10,20,0.92)';
    nctx.fillRect(0, 0, 256, 96);
    nctx.strokeStyle = '#ff5ea8';
    nctx.lineWidth = 5;
    nctx.strokeRect(4, 4, 248, 88);
    nctx.fillStyle = '#ff8ec4';
    nctx.font = 'bold 44px "Microsoft YaHei", sans-serif';
    nctx.textAlign = 'center';
    nctx.textBaseline = 'middle';
    nctx.fillText('PARTY', 128, 50);
    const neonTex = new THREE.CanvasTexture(neonCv);
    neonTex.colorSpace = THREE.SRGBColorSpace;
    const neon = new THREE.Sprite(new THREE.SpriteMaterial({ map: neonTex, transparent: true, depthWrite: false }));
    neon.scale.set(0.98, 0.37, 1);
    /* 牌挂在灯架上方，别被横梁劈成两半 */
    /* 挂在"远端"横梁外侧：不挡里面的人 */
    neon.position.set(DISCO.x, FLOOR_H + TR_Y + 0.3, DISCO.z - DR_D / 2 - 0.06);
    neon.userData.floor = 2;
    scene.add(neon);
    discoNeon = neon;

    /* 音箱放屋里：东侧两角，喇叭朝舞池 */
    [-1, 1].forEach((sgn) => {
      const sx = DISCO.x + DR_W / 2 - 0.34;
      const sz = DISCO.z + sgn * (DR_D / 2 - 0.42);
      B(0.26, 0.62, 0.26, M.darkMetal, sx, 0.33, sz, 0.02);
      C(0.1, 0.1, 0.02, M.metal, sx - 0.14, 0.44, sz, 14, { rz: Math.PI / 2, cast: false });
      C(0.06, 0.06, 0.02, M.metal, sx - 0.14, 0.24, sz, 12, { rz: Math.PI / 2, cast: false });
      OBSTACLES2.push([sx - 0.18, sz - 0.18, sx + 0.18, sz + 0.18]);
    });

    /* 玻璃墙当障碍（门洞留空，人能进去） */
    OBSTACLES2.push([DISCO.x - DR_W / 2 - 0.06, DISCO.z - DR_D / 2 - 0.06, DISCO.x + DR_W / 2 + 0.06, DISCO.z - DR_D / 2 + 0.06]);
    OBSTACLES2.push([DISCO.x - DR_W / 2 - 0.06, DISCO.z + DR_D / 2 - 0.06, DISCO.x + DR_W / 2 + 0.06, DISCO.z + DR_D / 2 + 0.06]);
    OBSTACLES2.push([DISCO.x + DR_W / 2 - 0.06, DISCO.z - DR_D / 2, DISCO.x + DR_W / 2 + 0.06, DISCO.z + DR_D / 2]);

    buildDanceSpots(DISCO.x, DISCO.z);

    /* 二层网格统一开启 layer 2：舞厅点光只照这一层，不会穿到一楼 */
    scene.traverse(o => {
      if ((o.isMesh || o.isLine) && o.userData.floor === 2) o.layers.enable(2);
    });

    /* 挂画两幅 */
    [[3.6, 0.9], [4.6, 0.9]].forEach(([x, y], i) => {
      B(0.5, 0.62, 0.03, M.frame, x, y + 0.35, -FD / 2 + 0.13, 0.01, { cast: false });
      B(0.42, 0.54, 0.01, std(i ? '#dfe9f4' : '#f2e8da', { r: 0.9 }), x, y + 0.35,
        -FD / 2 + 0.15, 0.005, { cast: false });
    });

    /* 地毯 + 绿植 + 楼层牌 */
    rug(6.2, 4.4, -1.2, -1.1, M.lounge);
    /* 左墙书架（带书） */
    B(0.38, 1.65, 2.1, M.wood, -6.35, 0.82, -1.2, 0.02);
    [0.35, 0.72, 1.09, 1.46].forEach(y => {
      B(0.34, 0.03, 2.0, M.deskEdge, -6.34, y, -1.2, 0.008, { cast: false });
      for (let i = 0; i < 9; i++) {
        const cols = ['#8fa9c9', '#c9a98f', '#9cc4a8', '#b9a7c9', '#d8c48f'];
        B(0.24, 0.22 + (i % 3) * 0.03, 0.13, std(cols[i % 5], { r: 0.9 }),
          -6.3, y + 0.13, -2.05 + i * 0.19, 0.004, { cast: false });
      }
    });
    OBSTACLES2.push([-6.6, -2.3, -6.1, -0.1]);

    /* 沙发角：地毯 + 双人沙发 + 茶几（整体右移，离开楼梯口） */
    rug(2.6, 2.0, -4.15, 2.35, M.lounge);
    /* 底座 1.9 宽 → 坐垫各 0.84，中心 ±0.46，整体在底座范围内 */
    B(1.9, 0.3, 0.8, M.chair, -4.15, 0.22, 3.05, 0.05);
    B(0.84, 0.13, 0.72, M.chair, -4.61, 0.43, 3.03, 0.05);
    B(0.84, 0.13, 0.72, M.chair, -3.69, 0.43, 3.03, 0.05);
    B(1.9, 0.42, 0.14, M.chair, -4.15, 0.52, 3.36, 0.04);
    /* 扶手（贴着底座两端） */
    B(0.14, 0.3, 0.78, M.chair, -5.02, 0.42, 3.03, 0.04);
    B(0.14, 0.3, 0.78, M.chair, -3.28, 0.42, 3.03, 0.04);
    C(0.34, 0.34, 0.05, M.wood, -4.15, 0.4, 2.05, 20, { cast: false });
    C(0.04, 0.04, 0.38, M.metal, -4.15, 0.2, 2.05, 8, { cast: false });
    OBSTACLES2.push([-5.15, 2.6, -3.15, 3.5]);

    /* 休息室（寝室）：两张躺椅 + 边几 + 地毯（右上角空地） */
    rug(3.4, 2.4, 5.0, -1.9, M.lounge);
    [-2.55, -1.35].forEach(z => {
      /* 躺椅：低矮的长条坐垫 + 靠背（躺上去的感觉） */
      B(1.05, 0.26, 1.9, M.chair, 5.0, 0.18, z, 0.06);
      B(1.02, 0.12, 1.86, M.chairDark, 5.0, 0.34, z + 0.02, 0.05);
      B(0.95, 0.5, 0.16, M.chair, 5.0, 0.55, z - 0.95, 0.05, { rx: -0.18 });
      /* 小枕头 */
      B(0.4, 0.12, 0.24, M.paper, 5.0, 0.44, z - 0.82, 0.04, { rx: -0.2 });
      /* 四条矮脚 */
      [[-0.45, -0.8], [0.45, -0.8], [-0.45, 0.8], [0.45, 0.8]].forEach(([dx, dz]) => {
        B(0.06, 0.16, 0.06, M.darkMetal, 5.0 + dx, 0.08, z + dz, 0.01, { cast: false });
      });
    });
    C(0.3, 0.3, 0.05, M.wood, 3.75, 0.42, -1.95, 20, { cast: false });
    C(0.04, 0.04, 0.4, M.metal, 3.75, 0.2, -1.95, 8, { cast: false });
    B(0.22, 0.02, 0.16, M.paper, 3.75, 0.47, -1.95, 0.008, { cast: false });
    OBSTACLES2.push([4.4, -3.55, 5.6, -0.35], [3.4, -2.3, 4.1, -1.6]);

    /* 打印机 + 边柜 */
    B(0.62, 0.72, 0.52, M.desk, 3.35, 0.36, 3.55, 0.02);
    B(0.5, 0.34, 0.44, M.darkMetal, 3.35, 0.9, 3.55, 0.02, { cast: false });
    B(0.44, 0.04, 0.34, M.paper, 3.35, 1.09, 3.55, 0.008, { cast: false });
    OBSTACLES2.push([3.0, 3.25, 3.72, 3.86]);

    /* 挂钟 */
    C(0.17, 0.17, 0.03, M.paper, -4.2, 1.35, -FD / 2 + 0.14, 20, { rx: Math.PI / 2, cast: false });
    C(0.18, 0.18, 0.02, M.metal, -4.2, 1.35, -FD / 2 + 0.155, 20, { rx: Math.PI / 2, cast: false });

    /* 绿植（新的程序化款） */
    /* 绿植：避开楼梯口（-6.0, 3.95）和沙发 */
    plant(-6.15, 1.55, 1.2);
    plant(5.95, 3.6, 1.1);
    plant(-5.95, -3.65, 1.15, '#3f8f57');
    OBSTACLES2.push([-6.45, 1.25, -5.85, 1.85], [5.65, 3.3, 6.25, 3.9], [-6.25, -3.95, -5.65, -3.35]);
    {
      const cv = document.createElement('canvas');
      cv.width = 256; cv.height = 128;
      const ctx = cv.getContext('2d');
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, 256, 128);
      ctx.fillStyle = '#2b3a4d';
      ctx.font = 'bold 64px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('2F', 128, 52);
      ctx.fillStyle = '#8fa2b8';
      ctx.font = '22px "Microsoft YaHei", sans-serif';
      ctx.fillText('PROJECT FLOOR', 128, 98);
      const t = new THREE.CanvasTexture(cv);
      t.colorSpace = THREE.SRGBColorSpace;
      const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.25), new THREE.MeshBasicMaterial({ map: t }));
      sign.position.set(-4.6, 1.05 + FLOOR_H, -FD / 2 + 0.14);
      sign.userData.floor = 2;
      scene.add(sign);
    }
  }
  buildingFloor = 1;
  buildingY = 0;

  buildStair(1);
  buildStair(2);

  const NAV = makeNav(OBSTACLES);
  const NAV2 = makeNav(OBSTACLES2);
  /* 二层座位挖口：不挖的话座位落在桌子的障碍里，会被判非法丢掉 */
  F2_DESKS.forEach(d => NAV2.carve(d.x, d.z + 0.65, 0, 0.62));
  F2_BENCH.forEach(x => NAV2.carve(x, -3.46, 0, 0.6));
  [4.95, 5.75].forEach(x => NAV2.carve(x, 3.15, 0, 0.6));
  [-2.55, -1.35].forEach(z => NAV2.carve(5.0, z + 0.15, 0, 0.7));
  NAV2.carve(F2_MEET.x, F2_MEET.z - 0.95, 0, -0.6);
  NAV2.carve(F2_MEET.x, F2_MEET.z + 0.95, 0, 0.6);
  /** 按楼层取导航网格 */
  const navFor = (f) => (f === 2 ? NAV2 : NAV);


  /* ================= 座位池 ================= */
  /* 站立位：沿过道/墙边均匀铺开，人多时不会挤成一堆 */
  const STAND = [
    [2.6, -0.9], [2.6, 0.1], [3.0, 3.9],
    [-5.4, -1.9], [-4.9, 1.5],
    [-3.5, 4.3], [-2.3, 4.3], [-0.8, 4.3], [1.7, 4.3],
    [-1.5, -3.7], [-0.4, -3.7], [0.7, -3.7],
    [3.6, -0.9], [4.7, -0.9],
    /* 扩容位：人多时沿着墙边站（办公室"站着开个短会"那种） */
    [-5.6, 0.2], [-5.6, 1.2], [5.8, 0.4], [5.8, 1.4],
    [0.4, 2.4], [1.6, 2.4], [0.2, -3.8], [5.8, 2.4]
  ];
  const SEAT_DEF = [];
  ['dA', 'dB', 'dC', 'dD'].forEach(k => SEAT_DEF.push({ key: k, kind: 'desk', ...SPOT[k] }));
  SEAT_DEF.push({ key: 'front', kind: 'front', ...SPOT.front });
  SEAT_DEF.push({ key: 'qc', kind: 'room', ...SPOT.qc });
  SEAT_DEF.push({ key: 'qc2', kind: 'room', ...SPOT.qc2 });
  ['coffee1', 'coffee2'].forEach(k => SEAT_DEF.push({ key: k, kind: 'coffee', ...SPOT[k] }));
  ['sofa1', 'sofa2'].forEach(k => SEAT_DEF.push({ key: k, kind: 'sofa', phone: true, ...SPOT[k] }));
  SEAT_DEF.push({ key: 'gym', kind: 'gym', ...SPOT.gym });
  /* 二层工位：两排 6 个 + 会议角 2 把椅子 */
  F2_DESKS.forEach((d, i) => {
    SEAT_DEF.push({
      key: 'e' + (i + 1), kind: 'desk', floor: 2,
      p: [d.x, d.z + 0.65], pose: 'work', ry: Math.PI, ap: [0, 0.55]
    });
  });
  F2_BENCH.forEach((x, i) => {
    SEAT_DEF.push({
      key: 'w' + (i + 1), kind: 'desk', floor: 2,
      p: [x, -3.46], pose: 'work', ry: Math.PI, ap: [0, 0.55]
    });
  });
  [4.95, 5.75].forEach((x, i) => {
    SEAT_DEF.push({
      key: 'p' + (i + 1), kind: 'coffee', floor: 2,
      p: [x, 3.15], pose: 'coffee', ry: Math.PI, ap: [0, 0.55], cup: true
    });
  });
  [-2.55, -1.35].forEach((z, i) => {
    SEAT_DEF.push({
      key: 'rest' + (i + 1), kind: 'room', floor: 2,
      p: [5.0, z + 0.15], pose: 'sitback', ry: 0, ap: [0, 0.6]
    });
  });
  SEAT_DEF.push({
    key: 'm1', kind: 'room', floor: 2,
    p: [F2_MEET.x, F2_MEET.z - 0.95], pose: 'work', ry: Math.PI, ap: [0, 0.55]
  });
  SEAT_DEF.push({
    key: 'm2', kind: 'room', floor: 2,
    p: [F2_MEET.x, F2_MEET.z + 0.95], pose: 'work', ry: 0, ap: [0, 0.55]
  });
  /* 露台：三张高脚桌各两个凳子 + 两个靠栏杆的站位 */
  [-2.9, 0, 2.9].forEach((x, i) => {
    const z = TERZ + (i % 2 ? 0.5 : -0.2);
    [-0.62, 0.62].forEach((dz, k) => {
      SEAT_DEF.push({
        key: `terrace${i}${k}`, kind: 'terrace',
        p: [x, z + dz], pose: 'sit', ry: Math.PI, ap: [0, -0.62]
      });
    });
  });
  SEAT_DEF.push({ key: 'terrace_rail1', kind: 'terrace', p: [-3.6, TERZ + 1.25], pose: 'stand', ry: Math.PI });
  SEAT_DEF.push({ key: 'terrace_rail2', kind: 'terrace', p: [3.6, TERZ + 1.25], pose: 'stand', ry: Math.PI });
  STAND.forEach((p, i) => SEAT_DEF.push({
    key: 'st' + i, kind: 'stand', p, pose: 'stand', ry: Math.PI * 0.25, ap: [0, 0.5]
  }));

  /* 丢掉落在障碍里的座位（防止人站进桌子里） */
  for (let i = SEAT_DEF.length - 1; i >= 0; i--) {
    const sp = SEAT_DEF[i];
    const nav = navFor(sp.floor || 1);
    const [c, r] = nav.toCell(sp.p[0], sp.p[1]);
    if (!nav.free(c, r)) SEAT_DEF.splice(i, 1);
  }

  const CAP = Math.min(48, SEAT_DEF.length);  // 最多同时渲染多少个人
  const PLATE_ALL = 12;                 // 少于这个数，所有人都显示名牌
  const PLATE_SOME = 22;                // 超过这个数，只显示"忙/待确认"

  /* 按状态挑座位的优先级 */
  const PREF = {
    busy: ['dA', 'dB', 'dC', 'dD', 'front', 'qc', 'coffee1', 'coffee2', 'sofa1', 'sofa2'],
    wait: ['qc', 'dA', 'dB', 'dC', 'dD', 'front'],
    /* 闲时：沙发 / 咖啡吧 / 工位（打游戏）交替，别让办公室空成一片桌子 */
    idle: ['sofa1', 'dA', 'coffee1', 'terrace_rail1', 'dB', 'sofa2', 'dC', 'gym', 'dD', 'coffee2', 'terrace_rail2', 'qc', 'front']
  };
  const LOUNGE = new Set(['sofa', 'coffee', 'gym']);

  function assignSeats(list, prevSeat, prevStatus) {
    const used = new Set();
    /* 访客占着的座位（会客室）不能被分给在岗的人 */
    agents.filter(r => r.temp && r.seat).forEach(r => used.add(r.seat.key));
    const out = [];
    const rank = a => (a.status === 'error' ? 0 : a.status === 'busy' ? 0 : a.status === 'wait' ? 1 : 2);
    const sorted = list.slice().sort((a, b) => rank(a) - rank(b));
    const picked = new Set();

    /* 组长先钉在前台 */
    const leader = sorted.find(a => a.isLeader);
    if (leader) {
      const fs = SEAT_DEF.find(s => s.key === 'front');
      if (fs) {
        used.add('front');
        picked.add(leader.id);
        out.push({ data: leader, seat: fs });
      }
    }

    /* 第一轮：**座位粘性** —— 老人留在原座位，轮询刷新时人不会来回跑 */
    sorted.forEach(a => {
      if (picked.has(a.id) || out.length >= CAP) return;
      const key = prevSeat && prevSeat.get(a.id);
      if (!key || used.has(key)) return;
      const s = SEAT_DEF.find(x => x.key === key);
      if (!s) return;
      /* 刚干完活的人：把工位让出来，去沙发/咖啡吧摸鱼（腾得出空位才走） */
      const wasBusy = prevStatus && prevStatus.get(a.id) === 'busy';
      if (wasBusy && a.status !== 'busy' && s.kind === 'desk') {
        const free = SEAT_DEF.find(x => LOUNGE.has(x.kind) && !used.has(x.key));
        if (free) return;
      }
      used.add(key);
      picked.add(a.id);
      out.push({ data: a, seat: s });
    });

    /* 第二轮：新人按状态偏好挑空位 */
    sorted.forEach(a => {
      if (picked.has(a.id) || out.length >= CAP) return;
      const pref = PREF[a.status] || PREF.idle;
      let seat = null;
      if (!used.has('front') && /主控|调度|总管/.test(a.role || '')) {
        seat = SEAT_DEF.find(s => s.key === 'front');
      }
      if (!seat) {
        for (const k of pref) {
          const s = SEAT_DEF.find(x => x.key === k);
          if (s && !used.has(k)) { seat = s; break; }
        }
      }
      if (!seat) seat = SEAT_DEF.find(s => !used.has(s.key));
      if (!seat) return;
      used.add(seat.key);
      picked.add(a.id);
      out.push({ data: a, seat });
    });
    return out;
  }

  /* ================= 自写 SSAO 后处理 ================= */
  const SS = 1.5;
  let rt = null;
  const postScene = new THREE.Scene();
  const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const postMat = new THREE.ShaderMaterial({
    uniforms: {
      tDiffuse: { value: null },
      tDepth: { value: null },
      uRes: { value: new THREE.Vector2(1, 1) },
      uNear: { value: camera.near },
      uFar: { value: camera.far },
      uHalf: { value: new THREE.Vector2(1, 1) },
      uRadius: { value: 0.28 },
      uStrength: { value: 0.72 },
      uBias: { value: 0.025 }
    },
    vertexShader: `
      varying vec2 vUv;
      void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
    `,
    fragmentShader: `
      uniform sampler2D tDiffuse;
      uniform sampler2D tDepth;
      uniform vec2 uRes;
      uniform float uNear, uFar;
      uniform vec2 uHalf;
      uniform float uRadius, uStrength, uBias;
      varying vec2 vUv;

      float lin(vec2 uv){ return uNear + texture2D(tDepth, uv).x * (uFar - uNear); }
      vec3 vpos(vec2 uv){
        return vec3((uv.x * 2.0 - 1.0) * uHalf.x, (uv.y * 2.0 - 1.0) * uHalf.y, -lin(uv));
      }

      void main(){
        vec3 base = texture2D(tDiffuse, vUv).rgb;
        float dd = texture2D(tDepth, vUv).x;
        if (dd >= 0.9995) { gl_FragColor = vec4(base, 1.0); return; }
        vec3 P = vpos(vUv);
        float radiusPx = uRadius / (uHalf.y * 2.0) * uRes.y;
        float occ = 0.0;
        float ang = 0.0;
        for (int i = 0; i < 16; i++){
          float fi = float(i);
          float r = sqrt((fi + 0.5) / 16.0) * radiusPx;
          ang += 2.39996323;
          vec2 off = vec2(cos(ang), sin(ang)) * r / uRes;
          vec3 S = vpos(vUv + off);
          float diff = S.z - P.z;
          if (diff > uBias) occ += clamp(1.0 - abs(diff) / uRadius, 0.0, 1.0);
        }
        float ao = clamp(1.0 - occ / 16.0 * uStrength, 0.28, 1.0);
        gl_FragColor = vec4(base * ao, 1.0);
      }
    `
  });
  postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMat));

  function resizeRT() {
    const pr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(2, Math.round(W() * pr * SS));
    const h = Math.max(2, Math.round(H() * pr * SS));
    if (rt) { rt.dispose(); rt.depthTexture.dispose(); }
    rt = new THREE.WebGLRenderTarget(w, h, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      type: THREE.UnsignedByteType
    });
    rt.depthTexture = new THREE.DepthTexture(w, h, THREE.UnsignedIntType);
    postMat.uniforms.tDiffuse.value = rt.texture;
    postMat.uniforms.tDepth.value = rt.depthTexture;
    postMat.uniforms.uRes.value.set(w, h);
    postMat.uniforms.uHalf.value.set(
      (camera.right - camera.left) / 2,
      (camera.top - camera.bottom) / 2
    );
  }
  resizeRT();

  /* ================= 运行时 ================= */
  const plates = opts.plates;
  const agents = [];
  let hoveredId = null;
  let selectedIdInner = null;

  /* 办公室级角标（挂在质检室上方）：目前承载"待你确认 N 项" */
  let badgeEl = null;
  function setBadge(text) {
    if (!badgeEl) {
      badgeEl = document.createElement('div');
      badgeEl.className = 'room-badge';
      /* 定位写死，宿主没写 CSS 也不会跑到左上角 */
      badgeEl.style.position = 'absolute';
      badgeEl.style.transform = 'translate(-50%,-100%)';
      badgeEl.style.pointerEvents = 'auto';
      badgeEl.style.cursor = 'pointer';
      badgeEl.addEventListener('click', e => {
        e.stopPropagation();
        if (opts.onBadgeClick) opts.onBadgeClick();
      });
      plates.appendChild(badgeEl);
    }
    badgeEl.textContent = text || '';
    badgeEl.style.display = text ? 'flex' : 'none';
  }
  const byId = new Map();
  let selectedId = null;

  function plateFor(a) {
    const el = document.createElement('div');
    el.className = 'ag-chip';
    el.dataset.id = String(a.data.id);
    el.addEventListener('click', e => {
      e.stopPropagation();
      selectedId = selectedId === a.data.id ? null : a.data.id;
      if (opts.onSelect) opts.onSelect(selectedId);
      refreshPlates();
    });
    plates.appendChild(el);
    return el;
  }

  /* ---------- 对话气泡：组长派活 / 组员回话 ---------- */
  const bubbleList = [];
  let nowT = 0;
  const esc = s0 => String(s0 || '').replace(/[<>&]/g, ch => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[ch]));

  function bubbleFor(rec) {
    let b = bubbleList.find(x => x.rec === rec);
    if (!b) {
      const el = document.createElement('div');
      el.className = 'ag-say';
      plates.appendChild(el);
      b = { rec, el };
      bubbleList.push(b);
    }
    return b;
  }

  /** 外部入口：冒一句气泡。kind='delegate' 时是「组长派给某人」 */
  function say(msg) {
    if (!msg || !msg.from) return;
    const rec = agents.find(r => r.data.name === msg.from);
    if (!rec) return;
    const b = bubbleFor(rec);
    const ttl = msg.kind === 'delegate' ? 8 : msg.kind === 'conclude' ? 9 : 6.5;
    b.until = nowT + ttl;
    const blue = msg.kind === 'delegate' || msg.kind === 'conclude';
    b.el.className = 'ag-say on' + (blue ? ' dl' : '');
    /* 派活计数：同一个人被连续点名 → 名牌上冒"忙到冒烟" */
    if (msg.kind === 'delegate' && msg.to) {
      const target = agents.find(r => r.data.name === msg.to);
      if (target) {
        target.tasks = (target.tasks || 0) + 1;
        refreshPlates();
      }
    }
    const body = esc(msg.text || msg.task || '');
    b.el.innerHTML = msg.kind === 'delegate'
      ? `<i class="who">派给 ${esc(msg.to || '组员')}</i>${body}`
      : body;
    b.el.style.display = 'block';
    /* 说话：嘴巴动起来；组长宣布结论时给个笑脸 */
    rec.talkUntil = nowT + Math.min(ttl, 4);
    if (msg.kind === 'conclude') {
      rec.person.setMood('happy');
      rec.moodUntil = nowT + ttl;
    }
  }

  /* ---------- 会开完了：组长走到白板前说结论，组员抬头听 ---------- */
  const WB_CANDIDATES = [[-5.2, -2.95], [-4.6, -2.85], [-4.0, -2.75], [-5.2, -3.4]];
  function wrapSpot() {
    for (const c of WB_CANDIDATES) {
      const [cx, cz] = NAV.toCell(c[0], c[1]);
      if (NAV.free(cx, cz)) return c;
    }
    return WB_CANDIDATES[0];
  }

  /** 走一段"临时路"：不改 rec.seat，所以下次轮询不会把人拽回去 */
  function walkTo(rec, x, z, ry, pose, onArrive) {
    rec.goal.set(x, z);
    rec.targetRy = ry;
    rec.targetPose = pose || rec.targetPose;
    const p = rec.person.root.position;
    rec.path = navFor((rec.seat && rec.seat.floor) || 1).findPath(p.x, p.z, x, z) || [];
    rec.wp = 0;
    rec.onArrive = onArrive || null;
    rec.person.setProp('none');
  }

  /** 扭头看某点（幅度限幅，别把头拧掉） */
  function lookAtPoint(rec, x, z, ttl) {
    if (!rec.person.head) return;
    const p = rec.person.root.position;
    let a = Math.atan2(x - p.x, z - p.z) - rec.person.root.rotation.y;
    while (a > Math.PI) a -= Math.PI * 2;
    while (a < -Math.PI) a += Math.PI * 2;
    rec.headYaw = Math.max(-0.85, Math.min(0.85, a));
    rec.person.head.rotation.y = rec.headYaw;
    rec.lookUntil = nowT + (ttl || 7);
  }

  function lookReset(rec) {
    rec.lookUntil = 0;
    rec.headYaw = 0;
    if (rec.person.head) rec.person.head.rotation.y = 0;
  }

  /**
   * 派活收尾：组长走到白板前公布结论，参会的组员抬头看他，7 秒后各自回座。
   * 这是"会开完了"的表演层，纯表现，不影响任何业务状态。
   */
  function wrapUp(opts) {
    const o = opts || {};
    const leader = agents.find(r => r.data.name === o.leader);
    if (!leader) return Promise.resolve();
    const spot = wrapSpot();
    return new Promise(resolve => {
      let fired = false;
      const fire = () => { if (!fired) { fired = true; resolve(); } };
      /* 兜底：走不到位也不能把结果弹窗一直卡着 */
      const guard = window.setTimeout(fire, 5000);
      // 站到白板前，面向房间（+z）
      walkTo(leader, spot[0], spot[1], Math.PI, 'stand', () => {
        window.clearTimeout(guard);
        say({ from: o.leader, text: o.text || '会开完了，结论我同步给大家。', kind: 'conclude' });
        (o.members || []).forEach(nm => {
          const r = agents.find(x => x.data.name === nm);
          if (r) lookAtPoint(r, spot[0], spot[1], 8);
        });
        window.clearTimeout(wrapUp._t);
        wrapUp._t = window.setTimeout(() => {
          agents.forEach(r => lookReset(r));
          if (leader.seat) moveTo(leader, leader.seat);
          disperse(o.members);   // 会开完了：参会的起身去喝口水
        }, 7200);
        fire();
      });
    });
  }

  /* ---------- 人流：散场、回工位、坐久了去摸鱼 ---------- */
  const LOUNGE_KINDS = new Set(['sofa', 'coffee', 'gym']);
  const DESK_KINDS = new Set(['desk']);
  /* 不在工位的座位：沙发 / 咖啡吧 / 健身角 / 露台。露台原本被漏掉，
     导致回工位、派活、摸鱼三处都当他是“坐着干活的人” */
  const OFF_DESK_KINDS = new Set(['sofa', 'coffee', 'gym', 'terrace']);

  /** 找一个这种类型的空座位（已被别人占的跳过） */
  function freeSeatByKind(kinds) {
    const taken = new Set(agents.map(r => r.seat && r.seat.key));
    return SEAT_DEF.find(x => kinds.has(x.kind) && !taken.has(x.key)) || null;
  }

  /** 同楼层优先的空工位：避免「人在 1F、座位分配在 2F」的穿层 */
  function freeDeskOnFloor(fl) {
    const taken = new Set(agents.map(r => r.seat && r.seat.key));
    return SEAT_DEF.find(
      x => x.kind === 'desk' && (x.floor || 1) === fl && !taken.has(x.key)
    ) || null;
  }

  /** 有活干了：在休息区的人陆续回工位 */
  function backToDesks() {
    agents.forEach((rec, i) => {
      if (rec.onDance) {
        rec.onDance = false;
        rec.singing = false;
        rec.holdSeat = false;
        rec.person.setProp('none');
      }
      if (!rec.seat || rec.data.isLeader) return;
      if (!OFF_DESK_KINDS.has(rec.seat.kind)) return;
      window.setTimeout(() => {
        const fl = (rec.seat && rec.seat.floor) || currentFloor || 1;
        const s = freeDeskOnFloor(fl) || freeSeatByKind(DESK_KINDS);
        if (s) moveTo(rec, s);
        else console.warn('[office3d] 回工位失败：没有空工位', rec.data.name);
      }, i * 700);
    });
  }

  /* ---------- 访客：外部智能体进门、在玻璃房开会、再走 ---------- */
  const visitors = [];   // 最多两位（会客室两把椅子）

  function visitorSeat() {
    const taken = new Set(visitors.map(r => r.seat && r.seat.key));
    return ['qc', 'qc2']
      .map(k => SEAT_DEF.find(x => x.key === k))
      .find(x => x && !taken.has(x.key)) || null;
  }

  /** 接待一位访客：从门口走到会客室（qc 座），门牌换成他的名字 */
  function visit(name, opts) {
    if (!name || visitors.length >= 2) return Promise.resolve(false);
    const seat = visitorSeat();
    if (!seat) return Promise.resolve(false);
    const rec = addAgent({
      data: { id: -Date.now(), name, status: 'idle', role: '访客', isLeader: false },
      seat
    });
    rec.temp = true;
    visitors.push(rec);
    setRoomSign(
      visitors.length > 1 ? `${visitors[0].data.name} 等 ${visitors.length} 位` : name,
      'VISITOR'
    );
    refreshPlates();
    /* 先站到门口，再走进会客室 */
    const p = rec.person.root.position;
    p.set(ENTRY[0], 0, ENTRY[1]);
    rec.pose = 'stand';
    rec.person.setPose('stand');
    rec.path = [];
    rec.wp = 0;
    window.setTimeout(() => moveTo(rec, seat), 500);
    window.setTimeout(() => {
      say({ from: name, text: (opts && opts.text) || '我是来对接的，先看看最近的数据。', kind: 'say' });
    }, 6200);
    const stay = (opts && opts.stay) || 20000;
    window.setTimeout(() => leaveVisitor(), stay);
    return Promise.resolve(true);
  }

  /** 送客：走出门再把人删掉；还有人就把门牌改成剩下那位 */
  function leaveVisitor() {
    const rec = visitors.pop();
    if (!rec) return;
    setRoomSign(
      visitors.length
        ? (visitors.length > 1
            ? `${visitors[0].data.name} 等 ${visitors.length} 位`
            : visitors[0].data.name)
        : '质检室',
      visitors.length ? 'VISITOR' : 'QUALITY CHECK'
    );
    walkTo(rec, ENTRY[0], ENTRY[1], Math.PI * 0.75, 'stand', () => {
      scene.remove(rec.person.root);
      if (rec.el) rec.el.remove();
      if (rec.dotEl) rec.dotEl.remove();
      const i = agents.indexOf(rec);
      if (i >= 0) agents.splice(i, 1);
      byId.delete(rec.data.id);
      refreshPlates();
    });
  }

  /* ---------- 会议：把几个人叫进玻璃房开会 ---------- */
  /* 会客室：两把椅子 + 三个站位（访客占着椅子时就站桌边） */
  const MTG_STANDS = [
    { key: '__mtg1', kind: 'room', p: [6.05, -3.1], pose: 'stand', ry: -Math.PI / 2 },
    { key: '__mtg2', kind: 'room', p: [3.6, -2.4], pose: 'stand', ry: Math.PI / 2 },
    { key: '__mtg3', kind: 'room', p: [3.6, -3.8], pose: 'stand', ry: Math.PI / 2 }
  ];

  function meeting(names, opts) {
    const list = (names || [])
      .map(nm => agents.find(r => r.data.name === nm))
      .filter(Boolean)
      .slice(0, 3);
    if (!list.length) return;
    setRoomSign('项目会议', 'MEETING');
    /* 访客坐着的椅子不能抢，剩下的用站位补 */
    const taken = new Set(visitors.map(r => r.seat && r.seat.key));
    const chairs = ['qc', 'qc2']
      .map(k => SEAT_DEF.find(x => x.key === k))
      .filter(x => x && !taken.has(x.key));
    const slots = [...chairs, ...MTG_STANDS];
    list.forEach((rec, i) => {
      if (!rec.homeSeat) rec.homeSeat = rec.seat;
      rec.holdSeat = true;            // 开会期间别被轮询叫回去
      const seat = slots[i];
      if (seat) window.setTimeout(() => moveTo(rec, seat), i * 900);
    });
    window.setTimeout(() => {
      say({ from: list[0].data.name, text: (opts && opts.text) || '把这几天的数据对齐一下，先看漏斗。', kind: 'say' });
    }, 5200);
    window.setTimeout(() => {
      list.forEach((rec, i) => {
        rec.holdSeat = false;
        const home = rec.homeSeat || rec.seat;
        rec.homeSeat = null;
        window.setTimeout(() => moveTo(rec, home), i * 800);
      });
      setRoomSign('质检室', 'QUALITY CHECK');
    }, (opts && opts.stay) || 24000);
  }

  /* 入口（房间前沿的空白处，进门就是过道） */
  const ENTRY = [5.75, 4.3];

  /**
   * 迟到的人从门口走进来：先站到入口外，再依次走到自己座位。
   * 纯表现；座位本身不变，所以轮询不会把人拽走。
   */
  function arriveLate(names, minutes) {
    const list = (names || [])
      .map(nm => agents.find(r => r.data.name === nm))
      .filter(Boolean);
    if (!list.length) return;
    list.forEach((rec, i) => {
      const p = rec.person.root.position;
      p.set(ENTRY[0] + i * 0.38, 0, ENTRY[1] + i * 0.12);
      rec.person.root.rotation.y = Math.PI * 0.75;
      rec.pose = 'stand';
      rec.person.setPose('stand');
      rec.path = [];
      rec.wp = 0;
      rec.lateMin = minutes || 0;
      window.setTimeout(() => {
        /* 迟到的人先回工位：座位在休息区的话，找一张空桌子 */
        const desk = LOUNGE_KINDS.has(rec.seat.kind) ? freeSeatByKind(DESK_KINDS) : null;
        moveTo(rec, desk || rec.seat);
      }, 700 + i * 1100);
    });
    refreshPlates();
  }

  /**
   * 散会：参会的人陆续起身去沙发/咖啡吧。
   * 只走一半（至少 1 个）——全走光工位一片空，反而不像"刚开完会"。
   */
  function disperse(names) {
    const list = names && names.length ? names : agents.map(r => r.data.name);
    const willing = list
      .map(nm => agents.find(r => r.data.name === nm))
      .filter(r => r && r.seat && !LOUNGE_KINDS.has(r.seat.kind));
    const quota = Math.max(1, Math.ceil(willing.length / 2));
    willing.slice(0, quota).forEach((rec, i) => {
      window.setTimeout(() => {
        const s = freeSeatByKind(LOUNGE_KINDS);
        if (s) moveTo(rec, s);
        else console.warn('[office3d] 散场失败：休息区满了', rec.data.name);
      }, 400 + i * 800);
    });
  }

  /* 空闲流动：在工位坐太久（默认 ~105 秒，按人错开）就起身去休息区，
     待一会儿（~70 秒）自己回工位。只动"待命"的人；出事的/干活的都不动。 */
  const IDLE_ROAM_BASE = 105;
  const IDLE_BACK_BASE = 70;
  let roamClock = 0;

  function maybeRoam() {
    const inLounge = agents.filter(r => r.seat && OFF_DESK_KINDS.has(r.seat.kind)).length;
    const cap = Math.max(1, agents.length - 2); // 别让全公司都在沙发上
    let acted = false;

    for (const r of agents) {
      if (acted) break;
      if (!r.seat || r.temp) continue;
      if (r.data.isLeader) continue;              // 组长钉在自己的位置，不摸鱼
      if (r.trip || r.chatting) continue;         // 正在跑腿/聊天：别被"去休息区"打断
      if (r.data.status !== 'idle') { r.roamSec = 0; continue; }
      if (r.path && r.wp < r.path.length) continue; // 正在走路，别打断

      r.roamSec = (r.roamSec || 0) + 1;
      const atDesk = r.seat.kind === 'desk';

      if (atDesk) {
        const need = IDLE_ROAM_BASE + (r.data.id % 7) * 11;
        if (r.roamSec < need || inLounge >= cap) continue;
        const s2 = freeSeatByKind(LOUNGE_KINDS);
        if (!s2) continue;
        r.homeSeat = r.homeSeat || r.seat;
        r.holdSeat = true;                         // 别被 20 秒轮询拽回工位
        moveTo(r, s2);
        r.roamSec = 0;
        acted = true;                              // 一次只走一个人，避免集体换座
      } else if (r.homeSeat && r.roamSec >= IDLE_BACK_BASE + (r.data.id % 5) * 8) {
        moveTo(r, r.homeSeat);
        r.homeSeat = null;
        r.holdSeat = false;
        r.roamSec = 0;
        acted = true;
      }
    }
  }

  /* ================= 生活感：接水/打印 跑腿 + 两人站着聊两句 ================= */
  /** 跑腿点：都取 STAND 里的空位（保证可走），语义上靠近饮水机 / 打印机 */
  const ERRANDS = [
    { key: 'water', p: [3.0, 3.9], ry: Math.PI, ms: [5000, 9000] },       // 咖啡吧/饮水机
    { key: 'printer', p: [5.8, 0.4], ry: -Math.PI / 2, ms: [5000, 9000] } // 打印区
  ];
  /** 聊天位：两两成对、面对面（STAND 里的空位，间距约 1.2） */
  const CHAT_PAIRS = [
    [[-3.5, 4.3], [-2.3, 4.3]],
    [[0.4, 2.4], [1.6, 2.4]],
    [[-0.4, -3.7], [0.7, -3.7]]
  ];
  let errandClock = 0;
  let chatClock = 0;

  /** 能安排"小动作"的人：待命、坐着、没在走路、没在跑腿/聊天 */
  function idlePool() {
    return agents.filter(r =>
      !r.temp && r.seat && !r.onDance && !r.trip && !r.chatting &&
      !r.homeSeat && r.data.status === 'idle' && !r.data.isLeader &&
      !(r.path && r.wp < r.path.length)
    );
  }

  /** 结束跑腿/聊天：清标记并回自己的座位 */
  function cancelTrip(rec, goHome = true) {
    const home = rec.trip && rec.trip.home;
    rec.trip = null;
    rec.chatting = false;
    rec.holdSeat = false;
    rec.homeSeat = null;
    if (goHome && home) moveTo(rec, home);
  }

  /** 每隔一阵挑一个闲着的人去接水 / 打印，站几秒再回来 */
  function maybeErrand() {
    const pool = idlePool().filter(
      (r) => r.seat.kind === 'desk' && !(r.errandAt && nowT - r.errandAt < 100)
    );
    if (!pool.length) return;
    const rec = pool[Math.floor(Math.random() * pool.length)];
    const job = ERRANDS[Math.floor(Math.random() * ERRANDS.length)];
    rec.errandAt = nowT;
    rec.trip = { home: rec.seat, kind: job.key };
    rec.holdSeat = true;
    moveTo(rec, {
      key: 'errand-' + job.key,
      kind: 'errand',
      floor: 1,
      p: job.p,
      pose: 'stand',
      ry: job.ry
    });
    const stay = job.ms[0] + Math.random() * (job.ms[1] - job.ms[0]);
    window.setTimeout(() => { if (rec.trip) cancelTrip(rec); }, stay);
  }

  /** 偶尔两个人站到一起聊几句：只做说话动作（点头/手势），不编造气泡内容 */
  function maybeChat() {
    const pool = idlePool();
    if (pool.length < 2) return;
    const shuffled = pool.slice().sort(() => Math.random() - 0.5);
    const r1 = shuffled[0];
    const r2 = shuffled[1];
    const pair = CHAT_PAIRS[Math.floor(Math.random() * CHAT_PAIRS.length)];
    const [p1, p2] = pair;
    const face = (from, to) => Math.atan2(to[0] - from[0], to[1] - from[1]);
    [[r1, p1, p2], [r2, p2, p1]].forEach(([rec, mine, other]) => {
      rec.chatting = true;
      rec.trip = { home: rec.seat, kind: 'chat' };
      rec.holdSeat = true;
      moveTo(rec, {
        key: 'chat',
        kind: 'chat',
        floor: 1,
        p: mine,
        pose: 'stand',
        ry: face(mine, other)
      });
    });
    /* 走过去站定（约 2.6 秒）再开始"说话"，聊 9 秒左右各自回座 */
    const until = nowT + 12;
    window.setTimeout(() => {
      r1.talkUntil = until;
      r2.talkUntil = until;
    }, 2600);
    window.setTimeout(() => {
      [r1, r2].forEach(rec => { if (rec.trip) cancelTrip(rec); });
    }, 12000);
  }

  /**
   * 派活：让这个人**真的动起来**——不在工位就先回工位，坐下进入工作状态。
   * 和面板里的支线是同一个 SSE 帧驱动的，所以两边永远一致。
   */
  function engage(name) {
    const rec = agents.find(r => r.data && r.data.name === name);
    if (!rec) return;
    /* 被派活：立刻退出舞池（不然会出现"一边跳舞一边干活"） */
    if (rec.onDance) {
      rec.onDance = false;
      rec.singing = false;
      rec.person.setProp('none');
    }
    rec.working = true;
    rec.holdSeat = true; // 别被轮询/摸鱼挪走
    rec.roamSec = 0;
    const atDesk = rec.seat && rec.seat.kind === 'desk';
    if (!atDesk) {
      const myFloor = (rec.seat && rec.seat.floor) || currentFloor || 1;
      const homeOk =
        rec.homeSeat && rec.homeSeat.kind === 'desk' && (rec.homeSeat.floor || 1) === myFloor;
      const desk = homeOk ? rec.homeSeat : (freeDeskOnFloor(myFloor) || freeSeatByKind(DESK_KINDS));
      rec.homeSeat = null;
      if (desk) moveTo(rec, desk);
    } else {
      // 已经在工位：直接进工作姿态（工位屏幕由 applyScreens 按 busy 切换）
      rec.person.setMood('busy');
    }
    refreshPlates();
  }

  /** 干完活：隔一两秒陆续起身去休息区（人满了就留在原位发呆） */
  function release(names) {
    const list = names && names.length
      ? names
      : agents.filter(r => r.working).map(r => r.data.name);
    list.forEach((nm, i) => {
      const rec = agents.find(r => r.data && r.data.name === nm);
      if (!rec) return;
      rec.working = false;
      window.setTimeout(() => {
        const cap = Math.max(1, agents.length - 2);
        const inLounge = agents.filter(r => r.seat && OFF_DESK_KINDS.has(r.seat.kind)).length;
        if (!rec.data.isLeader && inLounge < cap) {
          const s2 = freeSeatByKind(LOUNGE_KINDS);
          if (s2) {
            rec.homeSeat = rec.seat;
            moveTo(rec, s2);
            return;
          }
        }
        rec.holdSeat = false;
        rec.homeSeat = null;
      }, 1400 + i * 900);
    });
  }

  /**
   * 某人正在调某个工具：把工位屏幕切成对应画面。
   * 和面板里那一行工具是同一个事件——面板写什么，屏幕上就写什么。
   */
  function toolScreen(name, toolName) {
    const rec = agents.find(r => r.data && r.data.name === name);
    if (!rec) return;
    const t = String(toolName || '').toLowerCase();
    rec.toolKind = /sql|query/.test(t)
      ? 'sql'
      : (/search|kb|retriev|doc|prompt/.test(t) ? 'doc' : (/list|overview|camera|dataset|task/.test(t) ? 'list' : 'work'));
    rec.toolAt = performance.now();
    applyScreens();
  }

  /**
   * 被点名的人转一下头（看向组长），几秒后自己回正。
   * 只在"站着/坐着"时做，走路时不动，免得像抽筋。
   */
  function lookAtLeader(name, seconds = 4) {
    const rec = agents.find(r => r.data && r.data.name === name);
    const leader = agents.find(r => r.data && r.data.isLeader);
    if (!rec || !leader || rec === leader) return;
    const dx = leader.person.root.position.x - rec.person.root.position.x;
    const dz = leader.person.root.position.z - rec.person.root.position.z;
    const want = Math.atan2(dx, dz) - rec.person.root.rotation.y;
    let d = ((want + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
    d = Math.max(-1.15, Math.min(1.15, d)); // 脖子拧不到 180°
    rec.lookHead = d;
    rec.lookUntil = performance.now() + Math.max(1, seconds) * 1000;
  }

  let partyClock = 0;
  /* 手动清场后的「静默期」（秒）：用户点了清场就是不想再蹦，别再自作主张叫人来跳 */
  let partyMuteUntil = 0;

  /** 没人管的时候：偶尔自己凑一拨人去蹦（1~3 人） */
  function maybeParty() {
    if (!DANCE_SPOTS.length) return;
    if (nowT < partyMuteUntil) return;
    const idle = agents.filter(r =>
      !r.temp && !r.data.isLeader && r.data.status === 'idle' && !r.onDance &&
      !r.trip && !r.chatting &&
      !(r.path && r.wp < r.path.length)
    );
    const dancing = agents.filter(r => r.onDance).length;
    if (!idle.length || dancing >= DANCE_SPOTS.length) return;
    // 已经有人在跳，更容易凑过去；人少的时候一个人也进去蹦
    const want = Math.min(
      idle.length,
      1 + (dancing > 0 ? 1 : 0) + (agents.length >= 6 && Math.random() < 0.4 ? 1 : 0)
    );
    party(want);
  }

  /** 把 n 个待命的人叫到舞池跳舞（人不够就有几个来几个）；返回实际人数 */
  function party(count = 4) {
    if (!DANCE_SPOTS.length) return 0;
    const free = new Set(DANCE_SPOTS.map(s2 => s2.key));
    agents.forEach(r => { if (r.onDance) free.delete(r.seat.key); });
    const pool = agents.filter(r =>
      !r.temp && !r.data.isLeader && r.data.status === 'idle' && !r.onDance &&
      !r.trip && !r.chatting &&
      !(r.path && r.wp < r.path.length)
    );
    let n = 0;
    for (const rec of pool) {
      if (n >= count) break;
      const spot = DANCE_SPOTS.find(s2 => free.has(s2.key));
      if (!spot) break;
      free.delete(spot.key);
      /* 坐着被叫去蹦：先站起来。否则前几帧是「坐姿 + 蹦迪」的混合体，
         看起来就像"坐在沙发上蹦"。 */
      rec.idleAct = null;
      rec.standAt = 0;
      if (SEATED_POSES.has(rec.pose)) {
        rec.pose = 'stand';
        rec.person.setPose('stand');
      }
      /* homeSeat 只能是真正的座位：本来就在舞池的人，别把舞池当"家"，
         否则清场时会被送回来原地不动。 */
      rec.homeSeat = (rec.homeSeat && rec.homeSeat.kind !== 'dance')
        ? rec.homeSeat
        : (rec.seat && rec.seat.kind !== 'dance' ? rec.seat : null);
      rec.holdSeat = true;
      rec.onDance = true;
      rec.singing = n === 0;          // 第一个上来的拿话筒
      rec.person.setProp(rec.singing ? 'mic' : 'none');
      moveTo(rec, spot);
      n++;
    }
    refreshPlates();
    return n;
  }

  /**
   * 清场：所有人回座、放下话筒、并进入「静默期」——
   * 用户点了清场就是不想再蹦，25 秒后自动又开一场算 bug（实测会发生）。
   */
  function stopParty() {
    let moved = 0;
    agents.forEach(r => {
      if (!r.onDance) return;
      r.onDance = false;
      r.dancing = false;
      r.singing = false;
      r.person.setProp('none');
      /* 回自己的座位；没有（或在舞池/访客位）就找一个 1F 空工位，别把人扔在舞池里 */
      let back = r.homeSeat && r.homeSeat.kind !== 'dance' ? r.homeSeat : null;
      if (!back) back = freeDeskOnFloor(1) || freeSeatByKind(LOUNGE_KINDS);
      r.homeSeat = null;
      r.holdSeat = false;
      if (back) {
        moveTo(r, back);
        moved++;
      }
    });
    partyMuteUntil = nowT + 600;   // 10 分钟内不再自动开蹦
    refreshPlates();
    return moved;
  }

  /** 某一刻把某人拎出来闪一下（派活 / 调工具时，场景里同步有反馈） */
  /* ---------- 定时任务：到点自己开工 ---------- */
  /**
   * 定时任务不是"人派的活"，但办公室里同样要有交代：
   * 组长喊一声 → 负责人回工位坐下（工作屏幕亮起）→ 白板写任务/状态 → 跑完再报结果。
   * `status`：running / ok / error；`ms` 是这一轮耗时（毫秒）。
   */
  function cronRun(opts) {
    const o = opts || {};
    const name = o.name || '定时任务';
    const who = o.agent || '';
    const status = o.status || 'running';
    const done = status !== 'running';
    const secs = o.ms ? Math.max(1, Math.round(o.ms / 1000)) : 0;
    const leader = agents.find(r => r.data.isLeader);
    const rec = who ? agents.find(r => r.data.name === who) : null;

    if (leader) {
      say({
        from: leader.data.name,
        /* 有具体负责人 → 蓝底「派给 X」；只有调度器 → 普通气泡 */
        kind: done ? 'conclude' : (rec ? 'delegate' : 'say'),
        to: rec ? who : '调度器',
        text: done
          ? (status === 'error'
            ? `定时任务「${name}」没跑通，我记一笔`
            : `定时任务「${name}」跑完了，用时 ${secs} 秒`)
          : `到点了：定时任务「${name}」开始跑，${rec ? who + ' 负责' : '调度器负责'}`
      });
    }

    if (rec) {
      if (done) {
        rec.cronLabel = '';
        rec.person.setMood(status === 'error' ? 'tired' : 'happy');
        rec.moodUntil = nowT + 5;
        if (status === 'ok') ping(who);
        /* 跑完就下班：一两秒后起身去休息区，别一直挂着"工作中"。
           但只松开"这次定时任务叫起来"的人 —— 他要是本来在干别的活，别给放走。 */
        if (rec.cronBusy) {
          rec.cronBusy = false;
          release([who]);
        }
      } else {
        const wasWorking = !!rec.working;   /* 本来就在干活 → 跑完不归我们放 */
        engage(who);            /* 回工位、坐下、工作屏幕亮起 */
        rec.cronBusy = !wasWorking;
        ping(who);
        rec.cronLabel = name.length > 6 ? name.slice(0, 6) + '…' : name;
        rec.cronUntil = nowT + 120;
      }
      refreshPlates();
    }

    drawBoard([
      `定时任务：${name}`,
      rec ? `执行：${who}` : '执行：调度器',
      done ? (status === 'error' ? '结果：失败' : `结果：完成 · ${secs} 秒`) : '状态：进行中…'
    ]);
  }

  function ping(name) {
    const rec = agents.find(r => r.data.name === name);
    if (!rec || !rec.el) return;
    rec.el.classList.remove('ping');
    void rec.el.offsetWidth; // 重启动画
    rec.el.classList.add('ping');
    window.setTimeout(() => rec.el.classList.remove('ping'), 1400);
  }

  function clearBubbles() {
    bubbleList.forEach(b => { b.el.style.display = 'none'; b.until = 0; });
  }

  /* 工位屏幕：干活 = 工作界面；在岗 = 打游戏 / 看剧（按 id 稳定分配） */
  const DESK_KEYS = ['dA', 'dB', 'dC', 'dD', 'eA', 'eB', 'eC', 'eD'];
  function applyScreens() {
    const occupied = new Set();
    SCREEN_IN_USE.clear();
    agents.forEach(r => {
      const i = DESK_KEYS.indexOf(r.seat.key);
      if (i < 0) return;
      const m = DESK_SCREENS[i];
      if (!m) return;
      occupied.add(i);
      /* 正在调工具的人：屏幕切成对应的工具画面（SQL / 文档 / 列表），
         12 秒内优先于"忙碌/摸鱼"的默认画面 */
      const freshTool = r.toolKind && performance.now() - (r.toolAt || 0) < 12000;
      const kind = freshTool
        ? r.toolKind
        : (r.data.status === 'busy'
          ? 'work'
          : (r.data.id % 3 === 0 ? 'video' : (r.data.id % 3 === 1 ? 'game' : 'list')));
      r.screenKind = kind;          // postUpdate 按屏幕内容做"玩电脑"的姿态
      SCREEN_IN_USE.add(kind);      // 只重绘正在用的纹理
      m.map = SCREEN_TEX[kind];
      m.needsUpdate = true;
      const g = DESK_GLOWS[i];
      if (g) {
        g.color.set(kind === 'work' ? 0x8fbfe8 : kind === 'video' ? 0xffb86b : 0x8b8cff);
        /* 夜里：干活的桌前留一盏暖光，摸鱼的调暗（别整层楼都亮着） */
        g.opacity = kind === 'work' ? (night ? 0.85 : 0.55) : (night ? 0.18 : 0.7);
        if (night && kind === 'work') g.color.set(0xffcf8a);
      }
    });
    DESK_KEYS.forEach((k, i) => {
      if (occupied.has(i)) return;
      const m = DESK_SCREENS[i];
      if (m) { m.map = SCREEN_TEX.off; m.needsUpdate = true; }
      const g = DESK_GLOWS[i];
      if (g) { g.color.set(0xdfe6ef); g.opacity = night ? 0.03 : 0.25; }
    });
  }

  function refreshPlates() {
    const n = agents.length;
    agents.forEach(a => {
      const st = a.data.status;
      /* 名牌：人少全显示；人多只留 忙/等/选中/悬停（其余只留脚点） */
      const important = st === 'busy' || st === 'wait' || st === 'error';
      const focus = a.data.id === selectedId || a.data.id === hoveredId;
      const onFloor = ((a.seat && a.seat.floor) || 1) === currentFloor;
      const show = onFloor && (focus || important || n <= PLATE_ALL);
      if (a.dotEl) a.dotEl.style.display = onFloor ? '' : 'none';
      a.el.style.display = show ? 'flex' : 'none';
      a.el.className = 'ag-chip'
        + (st === 'wait' ? ' wait' : '')
        + (st === 'busy' ? ' busy' : '')
        + (st === 'error' ? ' err' : '')
        + (a.data.id === selectedId ? ' sel' : '');
      const role = '';
      const rawTask = (a.data.task || '').replace(/^组长派单：|^派单：/, '');
      const task = rawTask && show && st === 'busy' ? `<span class="tk">${rawTask}</span>` : '';
      const lead = a.data.isLeader ? '<span class="lead">组长</span>' : '';
      const hotN = a.tasks || 0;
      const hot = hotN >= 3 ? `<em class="hot">🔥 连派 ${hotN}</em>` : '';
      const ot = night && st === 'busy' ? '<em class="ot">加班</em>' : '';
      const late = a.lateMin ? `<em class="late">迟到 ${a.lateMin} 分</em>` : '';
      const vis = a.temp ? '<em class="vis">访客</em>' : '';
      /* 定时任务：没人派活，但得让人一眼看出"这是到点自己跑起来的" */
      const cron = a.cronLabel && nowT < (a.cronUntil || 0)
        ? `<em class="cron">⏰ ${a.cronLabel}</em>` : '';
      /* 协同：谁受了谁的命、组长在等谁 */
      const hb = a.assignedBy && nowT < (a.assignedUntil || 0)
        ? `<em class="hb">受命 · ${a.assignedBy}</em>` : '';
      const waitN = (a.awaitingList || []).length;
      const wt = a.awaiting && nowT < (a.awaitingUntil || 0)
        ? `<em class="hb wt">${waitN > 1 ? `并行等 ${waitN} 人` : `等 ${a.awaiting}`}</em>` : '';
      a.el.innerHTML = `<i class="dot ${st}"></i>${lead}<span class="nm">${a.data.name}</span>`
        + `${role}${vis}${cron}${hb}${wt}${late}${ot}${hot}${task}`;
    });
  }

  function addAgent(a) {
    const lite = agents.length >= 10;
    const person = useGltf ? makeGltfPerson(a.data.name) : makePerson(a.data.name, lite);
    const seat = a.seat;
    person.root.position.set(seat.p[0], seat.floor === 2 ? FLOOR_H : 0, seat.p[1]);
    person.root.userData.floor = seat.floor || 1;
    /* 零件也打上楼层标（否则切到 2F 时人被"拆散"藏起来）；
       人是在楼层切换之后才动态加的，所以这里要立刻按当前楼层决定显隐 */
    const pf = seat.floor || 1;
    person.root.traverse(o => {
      if (o.isMesh || o.isLine) {
        o.userData.floor = pf;
        if (pf !== currentFloor) {
          o.visible = false;
          o.userData.hiddenByFloor = true;   // 记一笔，切回这层时能还原
        }
      }
    });
    if ((seat.floor || 1) === 2) {
      person.root.traverse(o => { if (o.isMesh || o.isLine) o.layers.enable(2); });
    }
    person.root.rotation.y = seat.ry;
    person.setSeat && person.setSeat(seat);
    person.setPose(seat.pose);
    person.setProp(seat.cup ? 'cup' : (seat.phone ? 'phone' : 'none'));
    person.setMood(a.data.status === 'wait' || a.data.status === 'error' ? 'wait' : (a.data.status === 'busy' ? 'busy' : 'idle'));

    const rec = {
      data: a.data, seat, person,
      goal: new THREE.Vector2(seat.p[0], seat.p[1]),
      path: [], wp: 0,
      pose: seat.pose, targetPose: seat.pose,
      targetRy: seat.ry, moving: false, stuckT: 0
    };
    rec.el = plateFor(rec);
    const dot = document.createElement('i');
    dot.className = 'ag-dot ' + (a.data.status || 'idle');
    plates.appendChild(dot);
    rec.dotEl = dot;
    agents.push(rec);
    byId.set(a.data.id, rec);
    return rec;
  }

  /** 人的缩放补间（换楼层时"缩进楼梯口"再出来） */
  function scaleTo(rec, to, ms) {
    rec.scaleTween = {
      from: rec.person.root.scale.x || 1,
      to,
      t0: performance.now(),
      ms: Math.max(60, ms)
    };
  }

  function moveTo(rec, seat) {
    /* 跨楼层：先走到楼梯口，再换层，然后在新楼层走过去（不然会当场瞬移） */
    const fromFloor = rec.person.root.userData.floor || 1;
    const toFloor = seat.floor || 1;
    if (fromFloor !== toFloor) {
      walkTo(rec, STAIR.x, STAIR.z, Math.PI, 'stand', () => {
        scaleTo(rec, 0.62, 160); // 缩进楼梯口
        window.setTimeout(() => {
          rec.person.root.position.y = toFloor === 2 ? FLOOR_H : 0;
          rec.person.root.userData.floor = toFloor;
          /* 零件也要改楼层标，否则换层后身体被 setFloor 全部隐藏，只剩脚下一个 DOM 点 */
          rec.person.root.traverse(o => {
            if (o.isMesh || o.isLine || o.isSprite) {
              o.userData.floor = toFloor;
              const vis = toFloor === currentFloor;
              o.userData.hiddenByFloor = !vis;
              o.visible = vis;
            }
          });
          moveTo(rec, seat);
          scaleTo(rec, 1, 240); // 在新楼层展开
          /* 座位/楼层变了，名牌与脚下的小点要立刻跟着换层：
             以前只在 20 秒轮询时刷，导致 1F 视角下能看见 2F 的人的名牌悬在半空 */
          refreshPlates();
        }, 170);
      });
      return;
    }

    rec.seat = seat;
    rec.person.setSeat && rec.person.setSeat(seat);
    rec.movedAt = performance.now();
    const fy = seat.floor === 2 ? FLOOR_H : 0;
    if (rec.person.root.position.y !== fy) rec.person.root.position.y = fy;
    rec.person.root.userData.floor = seat.floor || 1;
    rec.goal.set(seat.p[0], seat.p[1]);
    rec.targetPose = seat.pose;
    rec.targetRy = seat.ry;
    const p = rec.person.root.position;
    const path = navFor(seat.floor || 1).findPath(p.x, p.z, seat.p[0], seat.p[1]);
    rec.path = path || [];
    rec.wp = 0;
    rec.person.setProp(seat.cup ? 'cup' : (seat.phone ? 'phone' : 'none'));
    /* 座位变了（含楼层），名牌/脚下点立刻刷新：不然 1F 视角会看到 2F 的人的名牌 */
    refreshPlates();
  }

  /** 外部入口：整体刷新 agent 列表 */
  function setAgents(list) {
    const prevSeat = new Map(agents.map(r => [r.data.id, r.seat.key]));
    const prevStatus = new Map(agents.map(r => [r.data.id, r.data.status]));
    const assigned = assignSeats(list || [], prevSeat, prevStatus);
    const keep = new Set(assigned.map(a => a.data.id));

    /* 删掉已经不存在的 */
    for (let i = agents.length - 1; i >= 0; i--) {
      const rec = agents[i];
      if (!keep.has(rec.data.id) && !rec.temp) {
        scene.remove(rec.person.root);
        rec.el.remove();
        agents.splice(i, 1);
        byId.delete(rec.data.id);
      }
    }
    /* 新增 / 更新 */
    assigned.forEach(a => {
      const rec = byId.get(a.data.id);
      if (!rec) { addAgent(a); return; }
      rec.data = a.data;
      /* 刚被散场/回工位/摸鱼挪过的人，4 秒内不跟轮询走：否则一次早于移动的
         轮询结果会把人拽回原座位，看起来像"走一半又退回去" */
      const justMoved = rec.movedAt && performance.now() - rec.movedAt < 4000;
      if (!rec.holdSeat && !justMoved && rec.seat.key !== a.seat.key) moveTo(rec, a.seat);
      rec.person.setMood(a.data.status === 'wait' || a.data.status === 'error' ? 'wait' : (a.data.status === 'busy' ? 'busy' : 'idle'));
    });
    refreshPlates();
    applyScreens();
  }

  /* ================= 循环 ================= */
  const v3 = new THREE.Vector3();
  const project = (x, y, z) => {
    v3.set(x, y, z).project(camera);
    return [(v3.x * 0.5 + 0.5) * W(), (-v3.y * 0.5 + 0.5) * H()];
  };

  const fx = { lastTrail: 0 };
  const pointer = { x: null, y: null };
  stage.addEventListener('pointermove', e => {
    const r = stage.getBoundingClientRect();
    pointer.x = e.clientX - r.left;
    pointer.y = e.clientY - r.top;
  });
  stage.addEventListener('pointerleave', () => {
    pointer.x = null; pointer.y = null;
    if (hoveredId != null) { hoveredId = null; refreshPlates(); }
  });
  stage.addEventListener('click', (ev) => {
    /* 只有点在 canvas 上才算"点场景"。
       面板、气泡、按钮这些 DOM 覆盖层都在 stage 里，事件会冒泡上来；
       以前不判来源，点「执行过程」里的任意一行都会被当成点空地 → 取消选中 → 面板被清空。 */
    if (ev.target && ev.target.tagName !== 'CANVAS') return;
    /* 看着大屏时，点一下场景就退回来（像游戏里退出看板） */
    if (scrState.mode !== 'idle') {
      closeScreen();
      return;
    }
    /* 点楼梯口 → 上下楼 */
    if (opts.onFloorSwitch) {
      const r0 = stage.getBoundingClientRect();
      const mx0 = ev.clientX - r0.left;
      const my0 = ev.clientY - r0.top;
      const [sx0, sy0] = project(STAIR.x, (currentFloor === 2 ? FLOOR_H : 0) + 1.18, STAIR.z);
      if (Math.hypot(mx0 - sx0, my0 - sy0) < 52) {
        opts.onFloorSwitch(currentFloor === 1 ? 2 : 1);
        return;
      }
    }
    selectedIdInner = (hoveredId && selectedIdInner !== hoveredId) ? hoveredId : null;
    selectedId = selectedIdInner;
    refreshPlates();
    if (opts.onSelect) opts.onSelect(selectedIdInner);
  });

  const clock = new THREE.Clock();
  let t = 0;
  let degraded = false, fAcc = 0, fCnt = 0;

  const lerpAng = (a0, a1, k) => {
    const d = ((a1 - a0 + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
    return a0 + d * k;
  };

  const _ba = new THREE.Vector3(), _bb = new THREE.Vector3(), _bm = new THREE.Vector3();

  /** 组长 → 每个"工作中"的组员画一条弧线，小点沿线流动 */
  function updateBeams(tt) {
    const leader = agents.find(r => r.data && r.data.isLeader);
    let bi = 0;
    const leaderOnFloor = leader
      ? (((leader.seat && leader.seat.floor) || 1) === currentFloor)
      : false;
    if (leader && leaderOnFloor) {
      const lp = leader.person.root.position;
      agents.forEach(r => {
        if (bi >= BEAMS.length || r === leader) return;
        if (r.data.status !== 'busy') return;
        /* 组员在另一层：这条弧线不该出现在当前楼层的空气里 */
        if ((((r.seat && r.seat.floor) || 1)) !== currentFloor) return;
        const tp = r.person.root.position;
        const b = BEAMS[bi];
        b.line.visible = true;
        b.dot.visible = true;
        _ba.set(lp.x, 1.15, lp.z);
        _bb.set(tp.x, 1.15, tp.z);
        _bm.copy(_ba).add(_bb).multiplyScalar(0.5);
        _bm.y = 2.05;
        const arr = b.geo.attributes.position.array;
        for (let i = 0; i < BEAM_N; i++) {
          const q = i / (BEAM_N - 1), u = 1 - q;
          arr[i * 3] = u * u * _ba.x + 2 * u * q * _bm.x + q * q * _bb.x;
          arr[i * 3 + 1] = u * u * _ba.y + 2 * u * q * _bm.y + q * q * _bb.y;
          arr[i * 3 + 2] = u * u * _ba.z + 2 * u * q * _bm.z + q * q * _bb.z;
        }
        b.geo.attributes.position.needsUpdate = true;
        b.geo.computeBoundingSphere();
        const k = (tt * 0.45 + bi * 0.19) % 1, ku = 1 - k;
        b.dot.position.set(
          ku * ku * _ba.x + 2 * ku * k * _bm.x + k * k * _bb.x,
          ku * ku * _ba.y + 2 * ku * k * _bm.y + k * k * _bb.y,
          ku * ku * _ba.z + 2 * ku * k * _bm.z + k * k * _bb.z
        );
        bi++;
      });
    }
    for (let i = bi; i < BEAMS.length; i++) {
      BEAMS[i].line.visible = false;
      BEAMS[i].dot.visible = false;
    }

    /* 失败弧：同样走二次贝塞尔，只是红色虚线、不依赖 busy 状态 */
    const nowMs = performance.now();
    const failOnFloor = failTarget
      ? (((failTarget.seat && failTarget.seat.floor) || 1) === currentFloor)
      : false;
    if (failTarget && leader && nowMs < failUntil && failOnFloor) {
      const lp = leader.person.root.position;
      const tp = failTarget.person.root.position;
      _ba.set(lp.x, 1.15, lp.z);
      _bb.set(tp.x, 1.15, tp.z);
      _bm.copy(_ba).add(_bb).multiplyScalar(0.5);
      _bm.y = 2.05;
      const arr = failGeo.attributes.position.array;
      for (let i = 0; i < FAIL_N; i++) {
        const q = i / (FAIL_N - 1), u = 1 - q;
        arr[i * 3] = u * u * _ba.x + 2 * u * q * _bm.x + q * q * _bb.x;
        arr[i * 3 + 1] = u * u * _ba.y + 2 * u * q * _bm.y + q * q * _bb.y;
        arr[i * 3 + 2] = u * u * _ba.z + 2 * u * q * _bm.z + q * q * _bb.z;
      }
      failGeo.attributes.position.needsUpdate = true;
      failLine.computeLineDistances();
      failLine.visible = true;
      const k = (tt * 0.8) % 1, ku = 1 - k;
      failDot.position.set(
        ku * ku * _ba.x + 2 * ku * k * _bm.x + k * k * _bb.x,
        ku * ku * _ba.y + 2 * ku * k * _bm.y + k * k * _bb.y,
        ku * ku * _ba.z + 2 * ku * k * _bm.z + k * k * _bb.z
      );
      failDot.visible = true;

      const tp2 = failTarget.person.root.position;
      failRing.position.set(tp2.x, tp2.y + 0.07, tp2.z);
      const beat = 1 + Math.sin(tt * 6) * 0.12;
      failRing.scale.set(beat, beat, beat);
      failRing.material.opacity = 0.45 + Math.sin(tt * 6) * 0.2;
      failRing.visible = true;
    } else {
      failLine.visible = false;
      failDot.visible = false;
      failRing.visible = false;
      if (failTarget && nowMs >= failUntil) failTarget = null;
    }
  }

  /** 取某个角色的"头"世界坐标；模型角色若没有头骨则退回脚点，避免整帧崩溃 */
  function headWorldPos(rec, v) {
    const h = rec.person.headAnchor || rec.person.head;
    (h || rec.person.root).getWorldPosition(v);
    return v;
  }

  /* WebGL 上下文被系统回收（休眠/切显卡/驱动重置）：不 preventDefault 就再也回不来 */
  let ctxLost = false;
  const onCtxLost = (e) => {
    try { e.preventDefault(); } catch (err) { /* 老浏览器可能不支持 */ }
    ctxLost = true;
    try { if (opts.onContextLost) opts.onContextLost(); } catch (err) { /* 回调别拖垮渲染 */ }
  };
  const onCtxRestored = () => {
    ctxLost = false;
    /* three 在恢复后会重建内部状态；这里强制刷新一次尺寸，保证下一帧画得出来 */
    try { renderer.setSize(W(), H(), false); } catch (err) { /* 忽略 */ }
    try { if (opts.onContextRestored) opts.onContextRestored(); } catch (err) { /* 忽略 */ }
  };
  const glCanvas = renderer.domElement;
  glCanvas.addEventListener('webglcontextlost', onCtxLost, false);
  glCanvas.addEventListener('webglcontextrestored', onCtxRestored, false);

  /* 页面切到后台就不画：省电、省 GPU（浏览器本来也会节流，但 WebGL 仍会跑） */
  let pageHidden = false;
  const onVisibility = () => {
    pageHidden = document.hidden;
  };
  document.addEventListener('visibilitychange', onVisibility);

  let frameCount = 0;
  /* 省电：手动开关（30fps + 关 SSAO）+ 窗口失焦自动降频（15fps）。
     办公场景是"氛围"性质，降频完全够看；e2e/无头浏览器不降频（否则用例会变慢变飘）。 */
  let lowPower = false;
  let skipCount = 0;
  let blurred = false;
  const AUTO_SLOW = !navigator.webdriver;
  if (AUTO_SLOW) {
    window.addEventListener('blur', () => { blurred = true; });
    window.addEventListener('focus', () => { blurred = false; });
  }
  function tick() {
    if (pageHidden || ctxLost) {
      /* 后台期间不推进时间：dt 有 0.05 上限，回来也不会瞬移 */
      requestAnimationFrame(tick);
      return;
    }
    if (lowPower || blurred) {
      /* 省电 30fps；只是失焦则 15fps（不降画质） */
      const every = lowPower ? 2 : 4;
      skipCount = (skipCount + 1) % every;
      if (skipCount) {
        requestAnimationFrame(tick);
        return;
      }
    }
    try { tickBody(); } catch (e) {
      console.error('[office3d]', e);
      /* 单帧逻辑出错不能连画面一起丢（曾经因为 person.tick 缺失把整屏冻在首帧） */
      try { renderFrame(); } catch (e2) { /* 渲染都挂了就没救了，别再刷屏 */ }
    }
    requestAnimationFrame(tick);
  }

  function tickBody() {
    frameCount++;
    const dt = Math.min(clock.getDelta(), 0.05);
    t += dt;
    tickHandoffs();

    if (t - roamClock >= 1) {
      roamClock = t;
      maybeRoam();
      /* 生活感：接水/打印（平均 ~45 秒一次）、两人站着聊两句（~70 秒一次） */
      if (Math.random() < 1 / 45) maybeErrand();
      if (Math.random() < 1 / 70) maybeChat();
      /* 有活干了的人：把跑腿/聊天收掉，别让人在饮水机旁边干活 */
      agents.forEach(r => {
        if ((r.trip || r.chatting) && r.data.status !== 'idle') cancelTrip(r);
      });
    }
    if (t - partyClock >= 25) {
      partyClock = t;
      if (Math.random() < 0.55) maybeParty();
    }

    /* 舞厅：**没人就关机**；有人在，灯跟"音乐节拍"走（人多 → 曲子更嗨、BPM 略高） */
    if (discoRig) {
      const dancers = agents.filter(r => r.onDance).length;
      const target = dancers > 0 ? 1 : 0;
      discoPower += (target - discoPower) * Math.min(1, dt * 3);   // 进出时淡入淡出
      const p0 = Math.max(0, Math.min(1, discoPower));

      const bpm = 104 + Math.min(4, dancers) * 6;                  // 1 人 110，5 人 128
      const beat = (t * bpm) / 60;
      const pulse = 0.5 + 0.5 * Math.sin(beat * Math.PI * 2);      // 0..1，一拍一次
      const every4 = (beat % 4) < 1 ? 1 : 0.82;                    // 每小节第一拍重一点

      if (p0 > 0.02) {
        discoRig.rotation.y = t * (0.55 + 1.1 * p0);
        if (discoBall) discoBall.rotation.y = t * (0.4 + 1.4 * p0);
        if (discoLightRef) {
          discoLightRef.color.setHSL((t * 0.1) % 1, 0.85, 0.6);
          discoLightRef.intensity = p0 * (2.6 + 2.2 * pulse * every4);
        }
        discoCones.forEach((c, i) => {
          /* 光锥是二层的东西：在一层看的时候必须收掉，
             否则 2F 开着聚光灯、1F 天花板上会冒出光柱（曾实测出现） */
          c.visible = currentFloor === 2;
          const off = (i % 2) * Math.PI;                            // 对角两束同拍
          const pk = 0.5 + 0.5 * Math.sin((beat + off / (Math.PI * 2)) * Math.PI * 2);
          c.material.opacity = p0 * (0.2 + 0.32 * pk);
          const sc = 1 + 0.06 * pk;
          c.scale.set(sc, 1, sc);
        });
        if (discoGlow) discoGlow.material.opacity = p0 * (0.35 + 0.5 * pulse);
        if (discoNeon) discoNeon.material.opacity = 0.25 + 0.75 * p0 * (0.7 + 0.3 * pulse);
        if (discoBall) discoBall.material.emissiveIntensity = 0.15 + 0.55 * p0 * (0.75 + 0.25 * pulse);
      } else {
        /* 关灯：光锥收掉、灯灭、霓虹只留一点、球停转 */
        discoCones.forEach(c => { c.visible = false; });
        if (discoLightRef) discoLightRef.intensity = 0;
        if (discoGlow) discoGlow.material.opacity = 0;
        if (discoNeon) discoNeon.material.opacity = 0.22;
        if (discoBall) discoBall.material.emissiveIntensity = 0.12;
      }
    }

    fAcc += dt; fCnt++;
    if (fCnt >= 24) {
      const avg = fAcc / fCnt; fAcc = 0; fCnt = 0;
      /* agent 多的时候自动降级，保证帧率 */
      if (avg > 0.055 && !degraded) { degraded = true; console.warn('[office3d] 关闭 SSAO'); }
    }

    agents.forEach(rec => {
      const p = rec.person.root.position;
      const hasWp = rec.path && rec.wp < rec.path.length;
      const tx = hasWp ? rec.path[rec.wp][0] : rec.goal.x;
      const tz = hasWp ? rec.path[rec.wp][1] : rec.goal.y;
      /* 在舞池的人：晃起来（只有"已经在舞池站好"才晃）。
         以前只判断 onDance，人被叫去蹦的头几帧还在坐姿里就开始上下颠，
         看起来就是"坐在沙发上蹦迪"。 */
      if (rec.onDance) {
        const moving2 = rec.path && rec.wp < rec.path.length;
        const baseY = (rec.person.root.userData.floor === 2 ? FLOOR_H : 0);
        const atDance = !!(rec.seat && rec.seat.kind === 'dance');
        if (!moving2 && atDance && !SEATED_POSES.has(rec.pose)) {
          const ph = (rec.data.id % 9) * 0.7;
          const amp = rec.singing ? 0.13 : 0.09;
          rec.person.root.position.y = baseY + Math.abs(Math.sin(t * 5 + ph)) * amp;
          rec.person.root.rotation.y = (rec.seat.ry || 0) + Math.sin(t * (rec.singing ? 3.4 : 2.6) + ph) * 0.32;
          rec.person.setMood('busy');
          if (rec.singing) {
            /* 唱歌：头微仰 + 手举到嘴边（话筒已经在手上） */
            if (rec.person.head) rec.person.head.rotation.x = -0.18 + Math.sin(t * 3.4) * 0.05;
          }
        } else {
          rec.person.root.position.y = baseY;
        }
      }

      if (rec.scaleTween) {
        const tw = rec.scaleTween;
        const k = Math.min(1, (performance.now() - tw.t0) / tw.ms);
        const sc = tw.from + (tw.to - tw.from) * k;
        rec.person.root.scale.setScalar(sc);
        if (k >= 1) rec.scaleTween = null;
      }

      /* 被点名看一眼组长：头慢慢转过去，几秒后自己回正 */
      if (rec.person.head) {
        const active = rec.lookUntil && nowT < rec.lookUntil;
        const inMeeting = rec.meetUntil && nowT < rec.meetUntil;
        /* 没人点名时，坐着的人也会偶尔自己扭头看看（发呆）；开会时更频繁 */
        if (!active && t > (rec.nextGlance || 0) &&
            (inMeeting || (rec.seat && rec.seat.pose && rec.seat.pose !== 'stand'))) {
          rec.nextGlance = t + (inMeeting ? 1.6 + Math.random() * 1.8 : 7 + Math.random() * 11);
          rec.lookHead = (Math.random() - 0.5) * (inMeeting ? 0.55 : 0.85);
          rec.lookUntil = nowT + (inMeeting ? 1.2 : 2.6);
        }
        const wantY = active ? (rec.lookHead || 0) : 0;
        if (rec.person.mixer) {
          /* 模型角色：骨骼每帧被 mixer 覆盖，这里只维护"想要的角度"，
             真正写骨骼在 postUpdate（mixer.update 之后） */
          rec.lookYaw = (rec.lookYaw || 0) + (wantY - (rec.lookYaw || 0)) * Math.min(1, dt * 5);
        } else {
          /* 开会时轻轻点头（在听人说话） */
          if (inMeeting) {
            rec.person.head.rotation.x = Math.sin(t * 4.2 + (rec.data.id % 7)) * 0.07;
          }
          rec.person.head.rotation.y += (wantY - rec.person.head.rotation.y) * Math.min(1, dt * 6);
        }
      }

      const dx = tx - p.x, dz = tz - p.z;
      const dist = Math.hypot(dx, dz);
      const arriveR = hasWp ? 0.06 : 0.03;

      /* 模型角色：动作由 AnimationMixer 驱动（坐着/走路/蹦迪/主唱/待机小动作） */
      if (rec.person.mixer) {
        rec.person.mixer.update(dt);
        if (dist > arriveR) {
          rec.person.setPose('walk');
          rec.idleAct = null;
        } else if (rec.onDance) {
          rec.person.setPose(rec.singing ? 'sing' : 'dance');
        } else if (rec.seat && rec.seat.pose && rec.seat.pose !== 'stand') {
          /* 工位坐着的人：每 26~56 秒来一次「看手机 / 发呆张望」 */
          const deskSeat = rec.seat.kind !== 'sofa' && rec.seat.kind !== 'coffee'
            && !/^w\d+$/.test(String(rec.seat.key || ''));
          if (deskSeat) {
            if (!rec.idleAct || t > rec.idleAct.until) {
              if (t > (rec.nextIdleAt || 0)) {
                const pool = ['sit_phone', 'sit_look'];
                rec.idleAct = { kind: pool[(Math.random() * pool.length) | 0], until: t + 5 };
                rec.nextIdleAt = t + 10 + Math.random() * 16;
              }
            }
            rec.person.setPose(rec.idleAct && t < rec.idleAct.until ? rec.idleAct.kind : 'sit');
          } else {
            rec.person.setPose('sit');
            rec.idleAct = null;
          }
        } else {
          /* 站着发呆：每隔 18~40 秒来一次伸懒腰 / 看手机 / 左右张望 */
          if (!rec.idleAct || t > rec.idleAct.until) {
            if (t > (rec.nextIdleAt || 0)) {
              const pool = ['stretch', 'phone', 'look'];
              rec.idleAct = { kind: pool[(Math.random() * pool.length) | 0], until: t + 4.2 };
              rec.nextIdleAt = t + 10 + Math.random() * 14;
            }
          }
          rec.person.setPose(rec.idleAct && t < rec.idleAct.until ? rec.idleAct.kind : 'idle');
        }
      }

      let stepped = false;
      if (dist > arriveR) {
        /* 坐着的人要走：先站起来（220ms），再迈步，避免腿"啪"一下从坐姿弹成走姿 */
        if (SEATED_POSES.has(rec.pose)) {
          if (!rec.standAt) {
            rec.standAt = t + 0.22;
            rec.pose = 'stand';
            rec.person.setPose('stand');
          }
          if (t < rec.standAt) {
            rec.moving = false;
            rec.person.tick && rec.person.tick(dt, t, false);
            return;
          }
        }
        /* 转身再走：背对着目标直接平移会"侧着滑过去"，很假。
           先原地转身（最多 0.4 秒），转到差不多正对再迈步。 */
        const wantRy = Math.atan2(dx, dz);
        const dAng = Math.atan2(
          Math.sin(wantRy - rec.person.root.rotation.y),
          Math.cos(wantRy - rec.person.root.rotation.y)
        );
        rec.person.root.rotation.y = lerpAng(
          rec.person.root.rotation.y, wantRy, Math.min(1, dt * 7)
        );
        if (Math.abs(dAng) > 0.85) {
          rec.walkSpeed = 0;
          if (rec.pose !== 'stand') { rec.pose = 'stand'; rec.person.setPose('stand'); }
        } else {
          /* 起步/收尾都缓一下（匀速平移像机器人）：每人速度略有差异，
             一群人去白板时才不会像复制粘贴。 */
          const base = 1.15 * (0.92 + ((rec.data.id || 0) % 5) * 0.04);
          const want = dist < 0.9 ? base * Math.max(0.35, dist / 0.9) : base;
          rec.walkSpeed = (rec.walkSpeed || 0) + (want - (rec.walkSpeed || 0)) * Math.min(1, dt * 6);
          const step = Math.min(dist, dt * Math.max(0.35, rec.walkSpeed || 0));
          p.x += dx / dist * step;
          p.z += dz / dist * step;
          stepped = true;
          if (rec.pose !== 'walk') { rec.pose = 'walk'; rec.person.setPose('walk'); }
          rec.person.setSpeed?.((rec.walkSpeed || 0) / 1.15);
        }
      } else if (hasWp) {
        rec.wp++;
      } else if (rec.pose !== rec.targetPose) {
        rec.walkSpeed = 0;
        rec.person.root.rotation.y = lerpAng(rec.person.root.rotation.y, rec.targetRy, Math.min(1, dt * 8));
        rec.pose = rec.targetPose;
        rec.standAt = 0;
        rec.person.setPose(rec.targetPose);
      }
      rec.moving = stepped;
      if (!rec.moving) rec.walkSpeed = 0;
      /* 到达判定仍按「离目标多近」算，不能按 moving：
         原地转身的那几帧 moving=false，但人还没到，提前触发 onArrive 会让人在半路坐下 */
      if (!rec.moving && dist <= arriveR && rec.onArrive) {
        const cb = rec.onArrive;
        rec.onArrive = null;
        cb();
      }
      if (rec.lookUntil && nowT > rec.lookUntil) lookReset(rec);

      if (rec.moving) {
        if (!rec.lastP) rec.lastP = { x: p.x, z: p.z };
        const moved = Math.hypot(p.x - rec.lastP.x, p.z - rec.lastP.z);
        rec.lastP.x = p.x; rec.lastP.z = p.z;
        rec.stuckT = moved < 0.004 ? rec.stuckT + dt : 0;
        if (rec.stuckT > 1.5) {
          rec.stuckT = 0;
          const np = navFor((rec.seat && rec.seat.floor) || 1).findPath(p.x, p.z, rec.goal.x, rec.goal.y);
          if (np && np.length) { rec.path = np; rec.wp = 0; }
          else { p.x = rec.goal.x; p.z = rec.goal.y; rec.path = []; rec.wp = 0; }
        }
      }
      rec.person.tick && rec.person.tick(dt, t, rec.moving);
      /* mixer 之后再补人味（扭头 / 说话点头 / 坐着打字）：
         模型角色的骨骼每帧被动画覆盖，只能放在这里写。 */
      if (rec.person.postUpdate) {
        rec.person.postUpdate(dt, t, {
          seated: SEATED_POSES.has(rec.pose),
          desk: !!(rec.seat && rec.seat.kind === 'desk'),
          moving: !!rec.moving,
          talking: !!(rec.talkUntil && nowT < rec.talkUntil),
          look: rec.lookYaw || 0,
          screen: rec.screenKind || '',
          seed: (rec.data.id % 7) * 0.6
        });
      }
    });

    /* 屏幕动画：200ms 一帧（省电 500ms），只重绘「当前有人用」的 kind。
       代码在滚、图表在跳、游戏画面在动、视频进度在走 —— 人盯着屏幕才不像木头。 */
    if (nowT - (fx.screenAt || 0) > (lowPower ? 0.5 : 0.2)) {
      fx.screenAt = nowT;
      SCREEN_IN_USE.forEach((kind) => {
        const cv = SCREEN_CV[kind];
        const tex = SCREEN_TEX[kind];
        if (!cv || !tex) return;
        paintScreen(cv.getContext('2d'), kind, nowT);
        tex.needsUpdate = true;
      });
      /* 屏幕前的光晕跟着画面轻微呼吸：远景看屏幕只有几十像素，
         光一明一暗才看得出"屏幕在动"（打游戏偏蓝、看视频偏暖） */
      agents.forEach((r) => {
        if (!r.screenKind) return;
        const i = DESK_KEYS.indexOf(r.seat.key);
        const g = i >= 0 ? DESK_GLOWS[i] : null;
        if (!g) return;
        const base = r.screenKind === 'work'
          ? (night ? 0.85 : 0.55)
          : (night ? 0.18 : 0.7);
        g.opacity = base * (0.86 + Math.sin(nowT * 2.1 + i * 1.7) * 0.14);
      });
    }

    /* 空闲流动：坐太久的人起身去休息区（每秒检查一次） */
    if (nowT - (fx.idleAt || 0) >= 1) {
      fx.idleAt = nowT;
      /* 休息区最多占 40%（至少 2 人）：全走了工位一片空，反而假 */
      const cap = Math.max(2, agents.length - 2);
      let inLounge = agents.filter(r => r.seat && OFF_DESK_KINDS.has(r.seat.kind)).length;
      agents.forEach((rec, i) => {
        if (rec.data.status !== 'idle') {
          rec.idleSec = 0;
          return;
        }
        rec.idleSec = (rec.idleSec || 0) + 1;
        if (rec.tasks && rec.idleSec > 120) {
          rec.tasks = 0;
          refreshPlates();
        }
        const limit = IDLE_ROAM_BASE + (i % 4) * 9;
        if (rec.idleSec < limit || !rec.seat || LOUNGE_KINDS.has(rec.seat.kind)) return;
        rec.idleSec = 0;
        if (inLounge >= cap) return;
        const s = freeSeatByKind(LOUNGE_KINDS);
        if (s) {
          moveTo(rec, s);
          inLounge++;
        }
      });
    }

    /* 人多了就不再互相推挤（开销大且容易抖动） */
    if (agents.length <= 16) {
      for (let i = 0; i < agents.length; i++) {
        for (let j = i + 1; j < agents.length; j++) {
          const A = agents[i], B = agents[j];
          if (!A.moving && !B.moving) continue;
          const pa = A.person.root.position, pb = B.person.root.position;
          const dx = pb.x - pa.x, dz = pb.z - pa.z;
          const d = Math.hypot(dx, dz);
          if (d > 0.36 || d < 0.0001) continue;
          const push = (0.36 - d) * 0.5, ux = dx / d, uz = dz / d;
          const tryMove = (per, sx, sz) => {
            const [c, r] = NAV.toCell(per.x + sx, per.z + sz);
            if (NAV.free(c, r)) { per.x += sx; per.z += sz; }
          };
          if (A.moving) tryMove(pa, -ux * push, -uz * push);
          if (B.moving) tryMove(pb, ux * push, uz * push);
        }
      }
    }

    updateBeams(t);

    /* 高亮：悬停优先，其次选中 */
    const focusId = hoveredId != null ? hoveredId : selectedIdInner;
    const focusRec = focusId != null ? agents.find(r => r.data.id === focusId) : null;
    const focusOnFloor = focusRec
      ? (((focusRec.seat && focusRec.seat.floor) || 1) === currentFloor)
      : false;
    if (focusRec && focusOnFloor) {
      const seat = focusRec.seat;
      const isDesk = ['dA', 'dB', 'dC', 'dD'].indexOf(seat.key) >= 0;
      HL.visible = true;
      HL.scale.set(isDesk ? 1.95 : 1.05, isDesk ? 1.55 : 1.05, 1);
      HL.position.set(seat.p[0], 0.062, seat.p[1] - (isDesk ? 0.32 : 0));
      HL.material.opacity = 0.10 + 0.04 * (focusId === selectedIdInner ? 1 : 0);
    } else {
      HL.visible = false;
    }

    /* 走动残影：每 0.3s 在脚下留一个，4s 内淡出 */
    if (t - (fx.lastTrail || 0) > 0.3) {
      fx.lastTrail = t;
      agents.forEach(rec => {
        if (!rec.moving) return;
        if (((rec.seat && rec.seat.floor) || 1) !== currentFloor) return;
        const p0 = rec.person.root.position;
        const tr = TRAILS[trailIdx % TRAIL_N];
        trailIdx++;
        tr.m.position.set(p0.x, 0.064, p0.z);
        tr.life = 1;
        tr.m.visible = true;
      });
    }
    TRAILS.forEach(tr => {
      if (tr.life <= 0) return;
      tr.life -= dt * 0.25;
      tr.m.material.opacity = Math.max(0, tr.life) * 0.18;
      if (tr.life <= 0) tr.m.visible = false;
    });

    /* 屏幕动效：工作界面缓慢滚动、游戏画面轻微抖动 */
    SCREEN_TEX.work.offset.y = (t * 0.04) % 1;
    SCREEN_TEX.game.offset.x = Math.sin(t * 2.2) * 0.003;
    SCREEN_TEX.game.offset.y = Math.cos(t * 1.7) * 0.003;

    if (badgeEl && badgeEl.style.display !== 'none') {
      const [bx, by] = project(4.8, 1.95, -3.1);
      badgeEl.style.left = bx + 'px';
      badgeEl.style.top = by + 'px';
    }

    nowT = t;

    /* 工牌跟随选中的人（始终面向镜头 + 一条引线） */
    if (badgeData.open) {
      const rec = badgeData.id != null ? byId.get(badgeData.id) : null;
      const badgeOnFloor = rec
        ? (((rec.seat && rec.seat.floor) || 1) === currentFloor)
        : false;
      if (rec && badgeOnFloor) {
        badgeMesh.visible = true;
        badgeLine.visible = true;
        const hp = new THREE.Vector3();
        headWorldPos(rec, hp);
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
        const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
        badgeMesh.quaternion.copy(camera.quaternion);
        badgeMesh.position.copy(hp).addScaledVector(right, 0.92).addScaledVector(up, 0.34);
        const grow = Math.min(1, (performance.now() - badgeData.t0) / 180);
        badgeMesh.scale.setScalar(0.9 + 0.1 * grow);
        const pos = badgeLine.geometry.attributes.position;
        pos.setXYZ(0, hp.x, hp.y + 0.06, hp.z);
        pos.setXYZ(1, badgeMesh.position.x - right.x * 0.6, badgeMesh.position.y - up.y * 0.3, badgeMesh.position.z - right.z * 0.6);
        pos.needsUpdate = true;
      } else if (!rec) {
        badgeData.mode = 'hidden';
        badgeData.data = null;
        badgeMesh.visible = false;
        badgeLine.visible = false;
      } else {
        /* 人在另一层：工牌先收起来，切回去还在 */
        badgeMesh.visible = false;
        badgeLine.visible = false;
      }
    }

    /* 镜头推拉（看大屏时聚焦，关掉时回原位） */
    if (camState.want) {
      const k = Math.min(1, dt * 3.6);
      camera.zoom += (camState.want.zoom - camera.zoom) * k;
      camera.updateProjectionMatrix();
      controls.target.x += (camState.want.tx - controls.target.x) * k;
      controls.target.y += (camState.want.ty - controls.target.y) * k;
      controls.target.z += (camState.want.tz - controls.target.z) * k;
      /* want.cam 存在时也平滑移动相机（正对白板/大屏）；不存在则把相机缓缓拉回默认位 */
      const wantCam = camState.want.cam || CAM_HOME;
      camera.position.x += (wantCam.x - camera.position.x) * k;
      camera.position.y += (wantCam.y - camera.position.y) * k;
      camera.position.z += (wantCam.z - camera.position.z) * k;
      if (
        Math.abs(camera.zoom - camState.want.zoom) < 0.01 &&
        Math.abs(controls.target.x - camState.want.tx) < 0.01
      ) {
        camera.zoom = camState.want.zoom;
        controls.target.set(camState.want.tx, camState.want.ty, camState.want.tz);
        const hc = camState.want.cam || CAM_HOME;
        camera.position.set(hc.x, hc.y, hc.z);
        camera.updateProjectionMatrix();
        camState.want = null;
        /* 聚焦完成后保持 camLock：不下发 controls.update()，否则它会把视角拽回默认 */
      }
    }
    const hp = new THREE.Vector3();
    agents.forEach((rec, idx) => {
      headWorldPos(rec, hp);
      const lift = 0.22 + (idx % 2) * 0.26;
      rec.lift = lift;
      const [sx, sy] = project(hp.x, hp.y + lift, hp.z);
      rec.el.style.left = sx + 'px';
      rec.el.style.top = sy + 'px';
    });

    /* 说话时嘴巴一开一合；说完/超时恢复常态表情 */
    agents.forEach((rec) => {
      const talking = rec.talkUntil && nowT < rec.talkUntil;
      if (talking) {
        const on = Math.floor(nowT * 7) % 2 === 1;
        if (rec.person.setTalking) rec.person.setTalking(on);
        rec.wasTalking = true;
      } else if (rec.wasTalking) {
        if (rec.person.setTalking) rec.person.setTalking(false);
        rec.wasTalking = false;
        if (rec.moodUntil && nowT > rec.moodUntil) {
          rec.person.setMood(rec.data.status === 'busy' ? 'busy' : 'idle');
          rec.moodUntil = 0;
        }
      }
    });

    /* 气泡跟着人走，超时就淡出 */
    bubbleList.forEach(b => {
      if (!b.until) return;
      if (nowT > b.until) {
        b.el.classList.remove('on');
        b.until = 0;
        setTimeout(() => { if (!b.until) b.el.style.display = 'none'; }, 200);
        return;
      }
      const rec = b.rec;
      if (!rec || !rec.person) return;
      /* 只显示本层的人：切到 1F 时，2F 的对话气泡不能飘到 1F 半空 */
      const onFloor = ((rec.seat && rec.seat.floor) || 1) === currentFloor;
      b.el.style.display = onFloor ? 'block' : 'none';
      if (!onFloor) return;
      headWorldPos(rec, hp);
      const [bx2, by2] = project(hp.x, hp.y + (rec.lift || 0.22) + 0.30, hp.z);
      b.el.style.left = bx2 + 'px';
      b.el.style.top = by2 + 'px';
    });

    /* 脚点跟随 + 悬停命中（屏幕距离最近的算） */
    let bestId = null, bestD = 1e9;
    agents.forEach(rec => {
      const p = rec.person.root.position;
      const [dx, dy] = project(p.x, p.y + 0.06, p.z);
      if (rec.dotEl) {
        rec.dotEl.style.display = ((rec.seat && rec.seat.floor) || 1) === currentFloor ? '' : 'none';
        rec.dotEl.style.left = dx + 'px';
        rec.dotEl.style.top = dy + 'px';
        rec.dotEl.className = 'ag-dot ' + (rec.data.status || 'idle')
          + (rec.data.id === selectedIdInner ? ' sel' : '')
          + (rec.data.id === hoveredId ? ' hov' : '');
      }
      if (rec.data.id === hoveredId) return;
    });
    if (pointer.x != null) {
      agents.forEach(rec => {
        const hp2 = new THREE.Vector3();
        headWorldPos(rec, hp2);
        const [hx, hy] = project(hp2.x, hp2.y, hp2.z);
        const d = Math.hypot(hx - pointer.x, hy - pointer.y);
        if (d < bestD) { bestD = d; bestId = rec.data.id; }
      });
      const next = bestD < 30 ? bestId : null;
      if (next !== hoveredId) {
        hoveredId = next;
        stage.style.cursor = next != null ? 'pointer' : 'grab';
        refreshPlates();
      }
    }

    /* 名牌防重叠：两两检测，后一个往上让 */
    const shown = agents.filter(r => r.el.style.display !== 'none');
    if (shown.length > 1) {
      const boxes = shown.map(r => ({ r, b: r.el.getBoundingClientRect() }));
      for (let pass = 0; pass < 3; pass++) {
        let moved = false;
        for (let i = 0; i < boxes.length; i++) {
          for (let j = i + 1; j < boxes.length; j++) {
            const A = boxes[i].b, B = boxes[j].b;
            const ox = Math.min(A.right, B.right) - Math.max(A.left, B.left);
            const oy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
            if (ox > 2 && oy > 1) {
              const el = boxes[j].r.el;
              const top = parseFloat(el.style.top) || 0;
              el.style.top = (top - (oy + 4)) + 'px';
              boxes[j].b = el.getBoundingClientRect();
              moved = true;
            }
          }
        }
        if (!moved) break;
      }
    }

    renderFrame();
  }

  /** 真正把画面画出来（与 tickBody 解耦：tickBody 半途抛异常时仍能出图，避免"整屏冻住"） */
  function renderFrame() {
    /* 阴影贴图每 4 帧刷一次（autoUpdate 已关，见 renderer 初始化处） */
    if (frameCount % 4 === 0) renderer.shadowMap.needsUpdate = true;
    if (!faceMode && !camLock) controls.update();
    if (degraded) {
      renderer.setRenderTarget(null);
      renderer.render(scene, camera);
    } else {
      renderer.setRenderTarget(rt);
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(postScene, postCam);
    }
  }

  const onResize = () => {
    aspect = W() / H();
    camera.left = -VIEW * aspect / 2;
    camera.right = VIEW * aspect / 2;
    camera.updateProjectionMatrix();
    renderer.setSize(W(), H());
    resizeRT();
  };
  addEventListener('resize', onResize);
  requestAnimationFrame(onResize);

  let faceMode = false;
  setFloor(1);
  drawScreen();
  setNight(null);
  const nightTimer = window.setInterval(() => {
    if (!document.hidden) setNight(null);
  }, 60000);

  tick();

  return {
    /* 验收用：把空闲计时拨到门槛，观察"起身去休息区 / 自己回工位"是否正常 */
    roamNow: () => {
      agents.forEach(r => {
        if (r.data.status === 'idle') r.roamSec = 999;
      });
    },
    /** 等角色模型加载完（失败也会 resolve false），页面先等它再排座 */
    ready: () => loadCharacter(),
    characterMode: () => (useGltf ? 'gltf' : 'procedural'),
    /** 验收用：6 个角色文件加载情况 + 每个 agent 分到哪套外观 / 坐姿走哪条重定向路线 */
    characterInfo: () => ({
      loaded: loadReport.map((r) => r.file + (r.ok ? ' ✓' : ' ✗')),
      sitRoute: charProtos.reduce((m, p) => { m[p.file] = p.sitRoute || '(未用到)'; return m; }, {}),
      agents: agents.map((r) => ({
        name: r.data.name,
        file: r.person.charFile || '(程序化小人)',
        cn: r.person.charName || '',
        seat: r.seat && r.seat.key,
        pose: r.pose
      }))
    }),
    debug: () => ({
      agents: agents.length,
      where: Object.fromEntries(agents.map(r => [
        r.data.name,
        [+r.person.root.position.x.toFixed(2), +r.person.root.position.z.toFixed(2), r.seat.key,
         +r.person.root.rotation.y.toFixed(2)]
      ])),
      beams: BEAMS.filter(b => b.line.visible).length,
      fail: !!(failTarget && performance.now() < failUntil),
      partying: agents.filter(r => r.onDance).map(r => r.data.name),
      power: +discoPower.toFixed(2),
      tools: agents.map(r => [r.data.name, r.toolKind || '-']),
      roam: agents.map(r => ({
        n: r.data.name,
        seat: r.seat && r.seat.key,
        sec: r.roamSec | 0,
        hold: !!r.holdSeat,
        moving: !!(r.path && r.wp < r.path.length)
      })),
      plates: [...document.querySelectorAll('.ag-chip')].filter(e => e.style.display !== 'none').map(e => e.textContent.trim()),
      sceneChildren: scene.children.length,
      list: agents.slice(0, 3).map(r => ({
        n: r.data.name,
        pos: [+r.person.root.position.x.toFixed(2), +r.person.root.position.y.toFixed(2), +r.person.root.position.z.toFixed(2)],
        kids: r.person.root.children.length, hipKids: r.person.hip.children.length, headY: r.person.head ? +r.person.head.getWorldPosition(new THREE.Vector3()).y.toFixed(2) : null,
        seat: r.seat && r.seat.key,
        plate: r.el ? r.el.style.display : 'none'
      }))
    }),
    setAgents,
    handoff,
    replyDone,
    leaderVisit,
    gatherAtBoard,
    kickoff,
    midSync,
    taskBoard: drawTaskBoard,
    setBadge,
    say,
    ping,
    toolScreen,
    failBeam,
    lookAtLeader,
    party,
    stopParty,
    partyCount: () => agents.filter(r => r.onDance).length,
    /** 验收用：已经画了多少帧（页面在后台时应该不再增长） */
    frames: () => frameCount,
    /** 验收用：WebGL 上下文现在是不是丢了 */
    contextLost: () => ctxLost,
    /** 验收用：当前活着的任务线数量（派活蓝线 + 回话绿线） */
    handoffs: () => HANDOFFS.length,
    /** 验收用：白板当前写的内容 */
    boardLines: () => lastBoardLines,
    /** 验收用：舞厅灯光到底有没有漏到别的楼层 */
    discoInfo: () => ({
      floor: currentFloor,
      power: +discoPower.toFixed(2),
      conesVisible: discoCones.filter(c => c.visible).length,
      conesTotal: discoCones.length,
      glow: !!(discoGlow && discoGlow.visible),
      neon: !!(discoNeon && discoNeon.visible),
      ball: !!(discoBall && discoBall.visible)
    }),
    /**
     * 验收用：本层视角里，还有没有"另一层的东西"露出来。
     * 扫全场可见网格，世界坐标高于二层楼板 90% 的都算可疑（1F 最矮的墙也到不了这个高度）。
     */
    floorLeak: () => {
      const out = [];
      const p = new THREE.Vector3();
      scene.traverse(o => {
        if (!(o.isMesh || o.isLine || o.isSprite || o.isPoints)) return;
        if (!o.visible) return;
        o.getWorldPosition(p);
        if (p.y > FLOOR_H * 0.9) {
          out.push({
            t: o.type,
            y: +p.y.toFixed(2),
            f: o.userData && o.userData.floor !== undefined ? o.userData.floor : 1,
            n: o.name || ''
          });
        }
      });
      return { floor: currentFloor, count: out.length, sample: out.slice(0, 10) };
    },
    writeBoard: (lines) => drawBoard(lines),
    engage,
    cronRun,
    release,
    wrapUp,
    disperse,
    backToDesks,
    arriveLate,
    visit,
    leaveVisitor,
    meeting,
    setScreen,
    screenMode: () => scrState.mode,
    closeScreen,
    showBadge,
    hideBadge,
    setLook,
    focusZone,
    focusFloor,
    focusAgent,
    cameraPreset,
    camDiag: () => {
      const bb = boardMesh.position, sg = scrGroup.position;
      const p = (vx, vy, vz) => { const v = new THREE.Vector3(vx, vy, vz); v.project(camera); return [+((v.x*0.5+0.5)).toFixed(3), +((-v.y*0.5+0.5)).toFixed(3)]; };
      return {
        board: { x: bb.x, y: bb.y, z: bb.z, px: p(bb.x, bb.y, bb.z) },
        screen: { x: sg.x, y: sg.y, z: sg.z, px: p(sg.x, sg.y, sg.z) },
        cam: { x: +camera.position.x.toFixed(2), y: +camera.position.y.toFixed(2), z: +camera.position.z.toFixed(2), zoom: +camera.zoom.toFixed(2) },
        target: { x: +controls.target.x.toFixed(2), y: +controls.target.y.toFixed(2), z: +controls.target.z.toFixed(2) },
        maxZoom: controls.maxZoom
      };
    },
    /* 调试/验收：无头环境 rAF 可能停摆，调用这个强制渲染一帧再截图 */
    renderNow: () => { try { renderFrame(); return true; } catch (e) { return false; } },
    scene,
    /* 验收用：把镜头推到某个人面前看细节（近景截图靠它，不改默认视角） */
    peek(name, zoom) {
      const rec = agents.find((r) => r.data.name === name) || agents[0];
      if (!rec) return null;
      const p = rec.person.root.position;
      const z = zoom || 4.5;
      controls.target.set(p.x, p.y + 0.95, p.z);
      /* 正常视角最大只到 2.4；验收要看脸，临时放开上限 */
      controls.maxZoom = Math.max(controls.maxZoom, z);
      camera.zoom = z;
      camera.updateProjectionMatrix();
      return [p.x, p.z];
    },
    resetView() {
      camState.want = null;
      controls.target.set(0.42, currentFloor === 2 ? FLOOR_H + 0.15 : 0.15, 0.12);
      controls.maxZoom = 2.4;
      camera.zoom = 1;
      camera.updateProjectionMatrix();
    },
    camera,
    controls,
    stairPos: () => project(STAIR.x, (currentFloor === 2 ? FLOOR_H : 0) + 1.18, STAIR.z),
    floor: () => currentFloor,
    /** 画质开关：low = 关 SSAO + 30fps（低配机器/省电用）；high = 全开 */
    setQuality: (q) => {
      lowPower = q === 'low';
      degraded = lowPower;
      skipCount = 0;
      return lowPower ? 'low' : 'high';
    },
    quality: () => (lowPower ? 'low' : 'high'),
    /** 验收用：立刻安排一次跑腿（接水/打印）/ 两人聊天，不等随机 */
    errandNow: () => {
      maybeErrand();
      return agents.filter((r) => r.trip && r.trip.kind !== 'chat').length;
    },
    chatNow: () => {
      maybeChat();
      return agents.filter((r) => r.chatting).length;
    },
    /**
     * 排查用：某个人的运行时状态（座位 / 姿态 / 当前动画 / 楼层标记统计）。
     * 楼层相关的 bug（人在 2F、身上还有零件算 1F）靠它定位，别删。
     */
    debugPerson(name) {
      const r = agents.find((x) => x.data && x.data.name === name);
      if (!r) return null;
      const byFloor = {};
      const visible = [];
      let meshes = 0;
      r.person.root.traverse((o) => {
        if (!(o.isMesh || o.isLine || o.isSprite)) return;
        meshes++;
        const f = o.userData.floor === undefined ? 'unset' : o.userData.floor;
        byFloor[f] = (byFloor[f] || 0) + 1;
        if (o.visible) visible.push(`${o.name || o.type}@${f}`);
      });
      return {
        seat: r.seat && {
          key: r.seat.key,
          kind: r.seat.kind,
          pose: r.seat.pose,
          floor: r.seat.floor || 1
        },
        pose: r.pose,
        targetPose: r.targetPose,
        onDance: !!r.onDance,
        singing: !!r.singing,
        /* 生活感小动作：跑腿（接水/打印）、两人聊天 */
        trip: r.trip ? { kind: r.trip.kind } : null,
        chatting: !!r.chatting,
        talking: !!(r.talkUntil && nowT < r.talkUntil),
        homeSeat: r.homeSeat ? r.homeSeat.key : null,
        hasPath: !!(r.path && r.wp < r.path.length),
        errandAt: r.errandAt || 0,
        nowT: +nowT.toFixed(0),
        action: r.person.currentAction ? r.person.currentAction() : null,
        face: r.person.faceKey ? r.person.faceKey() : null,
        screen: r.screenKind || '',
        y: +r.person.root.position.y.toFixed(2),
        floor: r.person.root.userData.floor || 1,
        meshes,
        byFloor,
        visible: visible.slice(0, 8)
      };
    },
    /**
     * 排查用：列出某个人物的骨骼 / 网格 / 材质名。
     * 找眼睛（眨眼）、脊柱（前倾）、头（扫视）用；模型换了也能一眼看出名字。
     */
    modelParts(name) {
      const r = agents.find((x) => x.data && x.data.name === name);
      if (!r) return null;
      const bones = [];
      const meshes = [];
      r.person.root.traverse((o) => {
        if (o.isBone) bones.push(o.name);
        else if (o.isMesh) meshes.push(`${o.name || '-'}|${(o.material && o.material.name) || '-'}`);
      });
      return { bones: bones.slice(0, 60), meshes: meshes.slice(0, 60) };
    },
    /** 验收用：强制某人做一个待机动作（stretch / phone / look / idle） */
    idleAct(name, kind) {
      const rec = agents.find((r) => r.data.name === name);
      if (!rec) return null;
      rec.idleAct = { kind, until: t + 8 };
      rec.nextIdleAt = t + 40;
      return kind;
    },
    /** 验收用：强制某人换表情 */
    face(name, mood) {
      const rec = agents.find((r) => r.data.name === name);
      if (!rec) return null;
      rec.person.setMood(mood);
      return mood;
    },
    /** 验收用：把所有人换成同一套发型（看发型长什么样） */
    setHair(idx) {
      agents.forEach((r) => {
        r.person.root.traverse((o) => {
          if (o.name && o.name.indexOf('hair_') === 0) o.visible = o.name.indexOf('hair_' + idx) === 0;
        });
      });
      return agents.length;
    },
    setNight,
    clearBubbles,
    select(id) { selectedId = id; refreshPlates(); },
    count: () => agents.length,
    dispose() {
      try { document.removeEventListener('visibilitychange', onVisibility); } catch (e) { /* 忽略 */ }
      try {
        glCanvas.removeEventListener('webglcontextlost', onCtxLost, false);
        glCanvas.removeEventListener('webglcontextrestored', onCtxRestored, false);
      } catch (e) { /* 忽略 */ }
      window.clearInterval(nightTimer);
      removeEventListener('resize', onResize);
      renderer.dispose();
      if (stage.contains(renderer.domElement)) stage.removeChild(renderer.domElement);
    }
  };
}
