Task 1: complete (commits 249755f..57f9b6b, review clean)
Task 2: complete (commits 57f9b6b..fd4c5ed, review clean after uuid fix)
Minor(t2): migration uuid col String(36) nullable vs ORM String(64) NOT NULL unique - align before final review
Task 3: complete (commits fd4c5ed..875c20a, review clean after patch-move fix)
Minor(t3): list_model_repos N+1 version_count; list_model_versions omits is_deleted filter; last-version by desc(id) not max version
Task 4: complete (commits 875c20a..d0797a0, review approved after queue-race + metrics-shape fixes)
Minor(t4): stop-before-dispatch window residual; lone -1 summary dropped if no real epoch; eval re-marks RUNNING after container finish
Task 5: complete (commits d0797a0..9de5a4a, review approved)
Minor(t5): _backtrack_export_path empty/None branch untested; predict model_id or repo_id fallback is dead code (model_id non-nullable)
Task 6: complete (commits 9de5a4a..8a3a63c, review approved after image-pull-order fix)
Minor(t6): paddlex CLI arg shapes unverified against real image; TrainEval/Predict.framework not persisted at create (inferred); paddlex eval metrics not parsed by YOLO parser; ultralytics predict zip drops label sidecars; _export_paddlex split shifts on failed download
Task 7: complete (commits 8a3a63c..45fd676, review approved; fixed real ordering bug export_model read best_metrics before write)
Minor(t7): 2 inspect-source tests brittle to formatting; map50 decimal vs percent display mismatch (deferred to Task 8); DB history metrics not auto-backfilled
Task 8: complete (see task-8-report.md; map50 shown as decimal in versions drawer)
Minor(t8): no repo create/delete endpoint (create_model_repo unrouted; delete_models only deletes versions) - repo delete leaves empty repo row; eval/predict/detail still jump with stale model_id param
Task 8: complete (commits 45fd676..19fed86, review approved after repo delete/create endpoint + nav fixes)
Minor(t8): create_model_repo always makes empty v1 version; name-dup silently appends version; delete_model_repos silent on missing ids; eval list uses watch not @change
Task 9: complete (commits 19fed86..a81be74, review approved after executor-offload fix)
Minor(t9): container.logs sync call on loop in failure path; _find_available_port residual concurrent first-deploy micro-race; health probe timeout overshoot ~4s; _container_exists conflates daemon-unreachable with absent
Task 10: complete (commits a81be74..db1966f, review approved; migration f1a2b3c4d5e6 fixed to create_type=False + applied to live DB)
Minor(t10): UI smoke test not executed (API-level + unit tests done); migration not defensive vs pre-existing table (create_all-before-migrations pattern)
ALL 10 TASKS COMPLETE. Remaining for human: browser UI smoke of train/eval/predict/deploy flows.
FINAL REVIEW: approved 'With fixes' -> all 6 Important fixed in bab2d15 -> re-review: Ready to merge = YES

=== SUBPROJECT 1: ultralytics enhancement (plan 2026-08-02-ultralytics-enhancement.md) ===
Baseline 92e2f84 (v3 port leftovers committed)
SP1 Task 1: complete (commits 92e2f84..c3268fe, review clean)
SP1 Task 2: complete (commits c3268fe..f6fca70, review approved)
Minor(sp1t2): multi-label split variance on small samples; inspect-source tests only; empty dirs if all images unlabeled
SP1 Task 3: complete (commits f6fca70..2e1f592, review approved)
Minor(sp1t3): hpForm defaults duplicated in onFrameworkChange; multi_label emitted for all tasks (UI-gated only)
SP1 Task 4: complete (commits 2e1f592..2760d97, review approved; residual paddlex branches in eval/predict/export_model deferred to SP2)
Minor(sp1t4): cleanup_paddlex_data leaves orphan repos w/ dangling latest_version_id; plugin.toml tags still lists paddlex
SP1 Task 5: complete (commits 2760d97..cd89939, review approved)
SP1 Task 6: complete (commits cd89939..2e780aa, review approved; DB already had 0 paddlex rows; script hardened)
Minor(sp1t6): orphan-repo predicate not paddlex-scoped; framework='PADDLEX' case-sensitive; UserModel import vestigial; paddlex-reject returns 500
SP1 ALL 6 TASKS COMPLETE (ultralytics enhancement). Remaining: final whole-branch review, then SP2 (PyTorch OCR).
SP1 final review: 2 Critical (lr0 binding, classification routing) + 4 Important fixed in 1d44eed; cls-model gap fixed in 6f91f65 -> re-review: Ready to merge = YES

=== SUBPROJECT 2: PyTorch OCR (plan 1 of 3: det model package + weight converter) ===
Baseline 27de05b (plan 1 doc committed)
SP2P1 Task 1: complete (commits 27de05b..e706d15, review approved; torch 2.13.0+cpu in venv)
IMPORTANT(sp2p1t1): rep()/fuse() even-kernel same-padding fusion is numerically wrong (latent; must fix before deploy/converter uses rep()); torch>=2.13 added as unconditional runtime dep (consider optional-dependency group later)
SP2P1 Task 2: complete (commits e706d15..44f9071, review approved; rep() fusion numerically verified ~1e-6)
Minor(sp2p1t2): out_channels no default; no len(in_channels)==4 assert; intracl attr not set False
SP2P1 Task 3: complete (commits 44f9071..9314f51, review approved; DBHead 4x upscale 640->640, brief placeholder corrected)
Minor(sp2p1t3): focal loss ignores shrink_mask; alpha uniform not per-class; loss weighting untested numerically (not bit-identical to PaddleOCR)
SP2P1 Task 4: complete (commits 9314f51..98c8ee3, review approved; pyclipper unclip, PaddleOCR-aligned)
SP2P1 Task 5: complete (commits 98c8ee3..9eb8235, review approved; positional-correspondence converter)
IMPORTANT(sp2p1t5): converter order-assumptions (Paddle save order = our reg order) NOT verifiable without Paddle env; DBHead index mismatch (conv2d_56 vs our conv2d_104) -> real weight verification REQUIRED in plan 3 paddlex container
Minor(sp2p1t5): _PARAM_MAP rank comment misleading; verify_conversion randn check weak
SP2P1 Task 6: complete (commits 9eb8235..68d7a85, review approved; 78 tests pass)
SP2 PLAN 1 ALL 6 TASKS COMPLETE (det model package + converter). Remaining: final whole-branch review, then plan 2 (Docker+train loop+backend) and plan 3 (inference+deploy+e2e).
SP2P1 final review: 2 Important (rep/fuse even-kernel padding, dilated_kernel_size) fixed in c1499fc; _same_asymmetric_pads generalized in 2ceb2d7 -> re-review: Ready to merge = YES
SP2 PLAN 1 COMPLETE (commits 27de05b..2ceb2d7, 83 tests, Ready to merge). Next: SP2 plan 2 (Docker image + train loop + backend integration).

=== SUBPROJECT 2: PyTorch OCR (plan 2 of 3: det training pipeline + backend integration) ===
Baseline 277cd48 (plan 2 doc committed)
SP2P2 Task 1: complete (commits 277cd48..3732437, review approved)
CROSS-TASK(sp2p2t1): shrink_mask semantics OPPOSITE to PaddleOCR (ours: 0=bg/1=text; Paddle: 1=bg) - Task2 DBLoss must align; no-bg-text images dropped from dataset (no hard negatives)
SP2P2 Task 2: complete (commits 3732437..915a247, review approved; smoke train produces best.pt)
CROSS-TASK(sp2p2t2): DetTrainer workers=4 default -> Windows spawn risk; Task5 executor must pass workers=0. Empty-dataset guard needed. image_shape (H,W) vs cv2.resize (W,H) only correct for square.
SP2P2 Task 3: complete (commits 915a247..1011e24, review approved; device-normalize fix in 95cb3eb)
Minor(sp2p2t3): eval-det doesn't coerce image_shape; test uses private argparse attrs
SP2P2 Task 4: complete (commits 1011e24..d1c76c0, Dockerfile delivered; no build per plan; docker --check blocked by network)
SP2P2 Task 5: complete (commits d1c76c0..9fac0d8, review approved; ENTRYPOINT fix correct, mount consistent)
Minor(sp2p2t5): cancel path may overwrite CANCELLED with FAILED (inherited TrainExecutor pattern); device vs gpu_id hyperparam mismatch; OCR image tag duplicated in service+executor; tests source-inspection only
SP2P2 Task 6: complete (commits 9fac0d8..f9f403c, review approved; backend contract matched)
Minor(sp2p2t6): OCR preview mounts /models ro (runtime doesn't); table formatter fallback shows PaddleX for unknown; onMounted implicit coupling
SP2P2 final review: 3 Important (cancel overwrite, gpu_id/device, empty dataset) fixed in 3ebba06 -> re-review: Ready to merge = YES
SP2 PLAN 2 COMPLETE (commits 277cd48..3ebba06, 95 tests, Ready to merge). Next: SP2 plan 3 (rec model + inference + deploy + e2e).

=== SUBPROJECT 2: PyTorch OCR (plan 3a of 3b: rec model package + weight converter) ===
Baseline 7f568dd (plan 3a doc committed)
SP2P3a Task 1: complete (commits 7f568dd..2f0d67d, review approved; official dict 6904 chars)
CROSS-TASK(sp2p3a t1): num_classes=6906 (blank=6905, chars=6905); pad token 0 collides with real char '!' (index 0) -> NRTRLoss ignore_index must not be 0 or label shift needed; broken-image infinite recursion inherited
SP2P3a Task 2: complete (commits 2f0d67d..c143d28, review approved; NRTR layer order verified, pe non-persistent)
CROSS-TASK(sp2p3a t2): NRTR state_dict order = ctc_head -> nrtr_head.linear -> embedding -> decoder.layers.0-3 -> tgt_word_prj (Task 6 converter uses this); label_gtc internal SOS handling (Task 3 NRTRLoss must match); Paddle real save-order unverified -> plan 3b
SP2P3a Task 3: complete (commits c143d28..4b8c669, review approved; NRTR length-mask -100 preserves real '!')
CROSS-TASK(sp2p3a t3): losses/__init__.py must export MultiLoss for RecTrainer import; NRTRLoss length-0 sample -> NaN
SP2P3a Task 4: complete (commits 4b8c669..a164e5f, review approved; teacher-forcing fix, smoke train best.pt)
Minor(sp2p3a t4): eval() still {} skeleton (plan 3b)
SP2P3a Task 5: complete (commits a164e5f..ac53fd6, review approved; CLI rec config correct)
SP2P3a Task 6: complete (commits ac53fd6..19503b7, review approved; head param silent misalignment flagged)
IMPORTANT(sp2p3a t6): rec converter head params silently misalign (12 wrong values, no warning) - positional regex only covers conv/bn, head Conv2d/Linear/LayerNorm interleaved. MUST add warning or fix before plan 3b consumers load rec weights. matched>0 only checks backbone.
SP2P3a Task 7: complete (commits 19503b7..ca9c36d, review approved; 115 tests)
SP2 PLAN 3a COMPLETE (commits 7f568dd..ca9c36d, 115 tests). Next: final branch review, then plan 3b.
SP2P3a final review: rec converter head-misalignment guard added in d4bebee -> re-review: Ready to merge = YES
SP2 PLAN 3a COMPLETE (commits 7f568dd..d4bebee, 116 tests, Ready to merge). Next: SP2 plan 3b (inference pipeline + deploy + backend rec integration + e2e including real weight verification).

=== SUBPROJECT 2: PyTorch OCR (plan 3b of 3b: inference + deploy + rec backend + e2e) ===
Baseline 95c4cbe (plan 3b doc committed)
SP2P3b Task 1: complete (commits 95c4cbe..d4aabf5, review approved; coordinate fix exact, e2e found detection)
Minor(sp2p3b t1): _recognize double-resize; _crop_box 90deg minAreaRect ambiguity (Task 7 e2e); rec path only tested when det finds box
SP2P3b Task 2: complete (commits d4aabf5..dced82c, review approved; CLI predict)
SP2P3b Task 3: complete (commits dced82c..61cc28b, review approved; OCRTrainExecutor shared base)
IMPORTANT(sp2p3b t3): PG enum trainframework needs ALTER TYPE ADD VALUE 'PYTORCH_OCR_REC' migration for live DB (det also skipped this - pre-existing gap); train_list.txt functional coverage missing
SP2P3b Task 4: complete (commits 61cc28b..f5c809d, review approved; frontend rec option)
SP2P3b Task 5: complete (commits f5c809d..1c30963, review approved; OCR server + deploy wiring)
IMPORTANT(sp2p3b t5): _launch passes ports=/entrypoint= to run_container (docker_utils doesn't accept) -> TypeError at launch, affects YOLO AND OCR deploy (pre-existing, never worked). MUST fix docker_utils + _launch before deploy usable.
SP2P3b Task 6: complete (commits 1c30963..efb1d6a, review approved; verify_conversion --rec)
SP2P3b Task 7: complete (commits efb1d6a..7a551bd, review approved; REAL e2e: image built, det weight MSE 1.68e-11, rec guard works)
MAJOR: PP-OCRv6 official det weights converted with MSE 1.68e-11 (486 params exact). Official weights use SEMANTIC names -> convert_by_name/map_semantic_name added. rec head name-mapping deferred (guard blocks silently). aistation-ocr image 9.81GB built.
Minor(sp2p3b t7): det converter lacks completeness guard (rec has it); base image 2.13.0 (env-driven); --break-system-packages contingent on Ubuntu 24.04
SP2P3b Task 8: complete (final regression; see sp2p3b-task-8-report.md; no code changes)
SP2 FINAL REGRESSION: backend pytest 129/129 PASS (~90s); ruff pytorch_ocr/ clean (88 FAST002 in controller.py pre-existing, last touched 19fed86 pre-SP2); frontend vue-tsc 0 errors + vite build OK; CLI smoke shows all 5 subcommands (train-det/eval-det/train-rec/eval-rec/predict).
SP2 (PyTorch OCR) ALL COMPLETE - 4 plans: P1 det model+converter, P2 det training+Docker+backend, P3a rec model+converter, P3b inference+deploy+rec backend+e2e. E2E: aistation-ocr image built, official PP-OCRv6 det weights MSE 1.68e-11, rec head mapping guarded. Deploy double-model (rec) skeletonized to single-model. Remaining for human: real docker deploy run (env network), rec weight head verification in container, browser UI smoke.
SP2P3b Task 8: complete (regression 129 pass; no code changes)
SP2 PLAN 3b COMPLETE (commits 95c4cbe..7a551bd, 129 tests). SP2 (PyTorch OCR) ALL 4 PLANS COMPLETE.
SP2 final review: 5 Important (rec channels, official vocab, deploy rec guard, real evals) fixed in 3637a0b -> re-review: Ready to merge = YES
SP2 (PyTorch OCR) FULLY COMPLETE: 4 plans, 38+ commits, 150 tests. Milestones: det weight MSE 1.68e-11, rec GTC weights strict-load, Hmean/char-acc evals, aistation-ocr image, real Docker e2e.
Minor(sp2): det eval BGR/RGB mismatch; NRTR greedy decode waste; cv2 arg order (W,H); degenerate-quad robustness
LIVE INFERENCE FIX: OCR now works with official weights! blank_idx=0 (official), rec [-1,1] norm, _crop_box minAreaRect fix. Reads: 'Hello World 你好世界' conf 0.955, 'AIStation OCR Test' 0.963, '模型训练测试123' 0.985. Commit c8d40f9, 150 tests.

=== PROGRAM: pipeline optimization (2026-09-11) ===
Branch: feat/pipeline-optimization
Baseline: 84632c4 (fakeredis test fix; 59 tests pass)
Plan 0A: docs/superpowers/plans/2026-09-11-pipeline-optimization-phase0a-backend-contract.md
0A Task 1: complete (commits 84632c4..ad6967a, review clean)
Minor(0A t1): executor skip/select fix not covered by regression test (only helper tested)
0A Task 2: complete (commits ad6967a..2655224, review clean)
0A Task 3: complete (commits 2655224..2d80c8a, review approved; brief deviations verified: status_code=404 + XFF + session fixture + 10 funcs)
Minor(0A t3): auth_headers session fixture returns shared mutable dict; positive delete test uses nonexistent id
0A Task 4: complete (commits 2d80c8a..0032baf, review approved)
Minor(0A t4): duplicate import try/except in registry; worker python may differ from backend; bool test weak
0A Task 5: complete (commits 0032baf..b961e61, review approved)
Minor(0A t5): first-run route guard redundant; constant test only checks route-name; scalar_one_or_none dup-row risk pre-existing
0A Task 6: complete (commits b961e61..5da0e43, review approved after per-statement transaction fix)
Minor(0A t6): fix behavior untested; missing_columns_for_model interface unimplemented; dup list between migration and schema_check
0A ALL 6 TASKS COMPLETE
0A FINAL REVIEW: Ready to merge = With fixes -> 2 Important (exception-probe blast radius, worker-interpreter gate) fixed in adf9e99 -> verified, 79 tests pass
Plan 0B: docs/superpowers/plans/2026-09-11-pipeline-optimization-phase0b-data-integrity.md
Plan 0C: docs/superpowers/plans/2026-09-11-pipeline-optimization-phase0c-frontend-harness.md
0B baseline: 463a74b
0B Task 1: complete (commits 463a74b..c4b601e, review approved)
Minor(0B t1): set_update_audit has no production callers yet (update paths still unset); thin integration coverage; other raw-construction sites unaudited
0B Task 2: complete (commits c4b601e..a7a6a74, review approved after test strengthening)
NEW BUG found by review: CRUDBase.page/list/tree_list skip is_deleted default filter when search empty (base_crud.py:93/128/178, condition built in __build_conditions:467-469) -> soft-deleted rows leak into unfiltered lists. Added as 0B Task 3.
0B Task 3: complete (commits 817e384..ecf25bd, review approved)
Minor(0B t3): unused _FAKE_PNG in test; list/tree_list paths not directly tested
0B ALL 3 TASKS COMPLETE
0C Task 1: complete (commits ecf25bd..f446efc, review approved; discovered+declared undeclared runtime dep vue-echarts; pnpm e2e 2 passed)
Minor(0C t1): baseURL /web path is a no-op (works via Vite redirect); smoke assertions coarse; README missing playwright install step
0C Task 2: complete (commits f446efc..a72213c, review approved after deploy-silent-failure + toast-test-retarget fixes; pnpm e2e 3 passed)
0C ALL 2 TASKS COMPLETE
PHASE 0 (0A+0B+0C) ALL TASKS COMPLETE
0B/0C FINAL REVIEW: Ready to merge = With fixes -> 4 Important (_silent on network/blob errors, updated_id on update paths, remaining duplicate toast, toast test hardening) fixed in deabe68+c05dd8d -> verification: all resolved, Ready to merge = YES
VERIFIED: backend pytest 86 passed; pnpm e2e 3 passed; type-check no new errors
PHASE 0 COMPLETE (0A+0B+0C).
Plan 1A: docs/superpowers/plans/2026-09-12-phase1a-export-correctness.md
1A baseline: 70860c7
1A Task 1: complete (commits 70860c7..f3ffd4b, review approved)
Minor(1A t1): -1/None class_id asymmetry between collector and formatter; absent class_id default mismatch; names always dict-form; extra_yaml raw interpolation
1A Task 2: complete (commits f3ffd4b..245a2f6, review approved; brief's rotation snippet corrected via min(x+y) canonicalization, mathematically verified 0..360deg)
Minor(1A t2): 90deg ordering under-tested; no branch-level OBB test; AxisAlignedBox obb alias unreachable
1A Task 3: complete (commits 245a2f6..46854fc, review approved; YAML parse independently verified)
Minor(1A t3): YAML parse verified; ragged keypoint counts rejected upstream; identity flip_idx
1A Task 4: complete (commits 46854fc..e5ef026, review approved)
IMPORTANT(1A t4): rotated-box computed in normalized space -> non-square images wrong; fixed for BOTH x-anylabeling and YOLO OBB in e5ef026 (pixel-space rotation) + non-square regression tests
Minor(1A t4): unrounded rotated floats; width or 0 vs or 1 fallback
1A Task 5: complete (commits e5ef026..65ab44f, review approved; official ppocrv6_dict NOT found in repo -> fallback charset + warning; dict not wired into training cmd)
1A ALL 5 TASKS COMPLETE
1A FINAL REVIEW: With fixes -> 3 Important (xany classification loss, official dict not used, -1/None class_id) fixed in 5e7b69c (vendored official ppocrv6_dict 18708 lines, classification flags, skip invalid ids) -> verification: all resolved, Ready to merge = YES
VERIFIED: backend pytest 106 passed
PHASE 1A COMPLETE (5 tasks). Next: 1B (工作台/导入/进度), 1C (统计/元数据).
Plan 1B: docs/superpowers/plans/2026-09-12-phase1b-workbench-import-progress.md
1B baseline: befc3d3
1B Task 1: complete (commits befc3d3..1311b69, review approved; also fixed SQLite jsonb_array_length->json_array_length)
Minor(1B t1): mysql branch emits jsonb fn; annotated subquery no record-level is_deleted (unreachable)
1B Task 2: complete (commits 1311b69..b1f6e15, review approved)
Minor(1B t2): renewal doesn't clear lockedByOther; a few race-only unguarded commit sites; CustomException code=409 not recognized by interceptor (generic msg)
1B Task 3: complete (commits b1f6e15..12c6349, review approved; pnpm e2e 4 passed with negative control)
Minor(1B t3): stale currentImageIndex across task nav (may load image N not first); removeClass always marks unsaved; e2e data not cleaned
1B Task 4: complete (commits 12c6349..3f693ad, review approved after fixes)
CRITICAL(1B t4): importer rotation computed in normalized space -> non-square wrong; fixed in 3f693ad (pixel-space) + duplicate-basename/cross-extension collision fixes
1B ALL 4 TASKS COMPLETE
1B FINAL REVIEW: With fixes -> 1 Critical (rotated-box export/import roundtrip) + 3 Important (stale image index, read-only mutations, removeClass dirty) fixed in dcd59c4+8295fa2 -> verification: all resolved, Ready to merge = YES
VERIFIED: backend pytest 116 passed; pnpm e2e 4 passed
PHASE 1B COMPLETE (4 tasks). Remaining Phase 1: 1C (统计页 422/语义 + 任务类定义/备注/批量接线).
Plan 1C: docs/superpowers/plans/2026-09-12-phase1c-stats-task-metadata.md
1C baseline: bc8c4d2
1C Task 1: complete (commits bc8c4d2..146c626, review approved; also db-agnostic func.date; pnpm e2e 5 passed)
Minor(1C t1): user_contributions vs total_annotations not consistent; dataset soft-delete does NOT cascade to annotation_task (orphan tasks counted); stats e2e guard narrow
1C Task 2: complete (commits 146c626..5a76f4c, review approved after form-alias + dict-classes fixes; e2e retries added, exit 0)
1C ALL 2 TASKS COMPLETE
PHASE 1 (1A+1B+1C) ALL TASKS COMPLETE
1C FINAL REVIEW: With fixes -> 1 Important (dataset delete doesn't cascade to tasks) + 3 cheap minors fixed in 4dddf8a+32a1945 -> verification: all resolved, Ready to merge = YES
VERIFIED: backend pytest 118 passed; pnpm e2e green
PHASE 1 (1A+1B+1C) COMPLETE. Next: Phase 2 (训练+评估).
Plan 2A: docs/superpowers/plans/2026-09-12-phase2a-train-scheduler-executor.md
2A baseline: 568a8b1
2A Task 1: complete (commits 568a8b1..138ca89, review approved)
Minor(2A t1): finally update out of inner try (can skip remaining schedules/mask success); new_id reset to None; success log removed; schedule model has no base_model_id column
2A Task 2: complete (commits 138ca89..df87a04, review approved; labels on train/eval/predict containers, stop-by-label, delete-running stops container, start guard)
IMPORTANT(2A t2, deferred): find_task_containers swallows Exception w/o log (fails open on daemon error); stop() vs _execute registry-population race (pre-existing)
2A Task 3 (重启重连) + Task 4 (base_model+并发) REMAIN; then 2B/2C/2D.
2A Task 3: complete (commits df87a04..6bc64a1, review approved after 2 fix rounds)
  - TrainExecutor full reattach via shared _finalize + artifact collection; PaddleX/eval/predict resolve to terminal FAILED (no restart artifact re-collection - documented follow-up); find_task_containers now logs on Docker error; registry-pop try/finally + cancel-status guard
VERIFIED: backend pytest 141 passed
2A Task 4 (base_model_id + GPU concurrency) REMAIN; then 2B/2C/2D.
2A Task 4: complete (commits 6bc64a1..a9d0b5e, review approved)
  - base_model_id wired (ultralytics model=/base/<name>; PaddleX pretrained) + global GPU semaphore across TrainExecutor/PaddleX det+rec
IMPORTANT(2A t4, deferred): reattach bypasses global semaphore (transient >limit after restart); concurrency gate has only source-string test (no behavioral serialization test)
PHASE 2A COMPLETE (4 tasks). Final 2A whole-branch review still pending. Next: 2B (指标解析与训练详情).
Plan 2B: docs/superpowers/plans/2026-09-12-phase2b-metrics-detail.md
2B baseline: de6bcdf
2B Task 1: complete (commits de6bcdf..65c67d0, review approved after fixes)
  - unified metrics.py (primary_metric_key/best_metric); PaddleX det keeps hmean (select_paddlex_best fallback); no-artifact export_model skips DB insert; ultralytics no-artifact -> FAILED
FOLLOWUP(2B t1): PaddleX model-version row metrics not backfilled with fresh best (export_model called before select_paddlex_best)
2B Task 2 (训练详情前端按框架展示) REMAIN.
2B Task 2: complete (commits 7790431..0949df5, review approved after live-cls fix)
  - train detail framework-aware metrics (metricSpec); running cls parses top1/top5; PaddleX epoch total fallback
PHASE 2B COMPLETE (2 tasks). Next: 2C 评估链路.
Plan 2C: docs/superpowers/plans/2026-09-12-phase2c-eval-pipeline.md
2C baseline: 0528357
2C Task 1: complete (commits 0528357..eed5b43, review approved after YAML path fix)
  - eval full deterministic export (for_eval all->val); resolve_eval_context passes annotation_task_id + mode/size; start_evaluation clears state; cls top1/top5 parse; dataset.yaml path=/data
Minor(2C t1): cls eval uses data=*.yaml (pre-existing, may need dir); legacy model_repo_id-as-repo-id degrades to det/tiny
2C Task 2: complete (commits eed5b43..20f1367, review approved)
  - eval create sends selected model_id/repo_id; export dialog uses model_id; eval detail framework-aware; extracted utils/trainMetrics.ts (shared w/ task detail)
PHASE 2C COMPLETE (2 tasks). Next: 2D 仓库/导出/下载一致性.
Plan 2D: docs/superpowers/plans/2026-09-12-phase2d-repo-export-download.md
2D baseline: 8a082e8
2D Task 1: complete (commits 8a082e8..473c5ce, review approved + directory-export URL fix)
  - object_exists + resolve_download_target (export_service); download_model returns truthful format/re-downloadable; directory export URL points to real key
2D Task 2 (模型编辑字段/状态 + 模型下拉分页) REMAIN.
2D Task 2: complete (commits 473c5ce..b79d975, review approved)
  - repo edit round-trips annotation_dataset_id + status; model dropdowns page_size=100 across eval/predict/deploy; backend status-persistence test
PHASE 2 COMPLETE (2A+2B+2C+2D). Next: Phase 3 (预测/部署/视频推理).
Plan 3A: docs/superpowers/plans/2026-09-12-phase3a-predict.md
3A baseline: c0afa78
3A Task 1: complete (commits c0afa78..5cd7aa2, review approved)
  - predict_gpu_id + build_predict_cmd (PaddleX single -o, use_gpu from device, ultralytics device=); rec dataset export ocr_rec
Minor(3A t1): model_filename shell quoting; predict_gpu_id non-numeric passthrough
3A Task 2: complete (commits 5cd7aa2..800fb83, review approved + atomic start guard)
  - sign_predict_results (keys<->URLs, legacy compatible) in get/list; delete_predicts cleans prefix; _execute stores keys; start_prediction atomic guard
FOLLOWUP: start_training/start_evaluation guards are non-atomic too (apply same atomic pattern)
PHASE 3A COMPLETE (2 tasks). Next: 3B 部署生命周期与脚本.
Plan 3B: docs/superpowers/plans/2026-09-12-phase3b-deploy.md
3B baseline: 2dfefd3
3B Task 1: complete (commits 2dfefd3..e3241cd, review approved after 2 fix rounds)
  - deploy labels, registry rehydrate (adopted re-probe), periodic reconcile, stop real container (registry->DB->label), normal-exit status, port reuse active-only, renew refuses deploying, delete stops first
3B Task 2 (部署脚本规格驱动/rec 裁剪/超参透传) REMAIN.
3B Task 2: complete (commits e3241cd..67ba42b, review approved after spec-fallback/crop fixes)
  - resolve_deploy_spec (invalid-value fallback), PaddleX cfg by size, rec crops box (skip OOB), ultralytics conf/iou/imgsz passthrough, conditional pip install
PHASE 3B COMPLETE (2 tasks). Next: 3C 视频推理.
Plan 3C: docs/superpowers/plans/2026-09-12-phase3c-inference.md
3C baseline: 6478d19
DECISION: 布控改走 ModelDeploy Server 架构。新增专用'布控 Agent'(基于 ModelDeploy SDK，不动 surveillance)，AIStation 做云边协同(边缘 MQTT/纯云端 HTTP)+设备能力管理与任务编排。
Spec: docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md
ModelDeploy 会话交接: docs/superpowers/specs/2026-09-12-modeldeploy-agent-handoff.md
Commit: cd0e82f
Phase 3C 原方案作废，按新 spec 重写 AIStation 侧接入。
Phase 3C re-written -> docs/superpowers/plans/2026-09-12-phase3c-edge-agent-integration.md (supersedes 2026-09-12-phase3c-inference.md).
3C baseline: 88565bd
3C Task 1: complete (commits 88565bd..435eedf, review approved after secret-mask/pagination/heartbeat-warning/DDL fixes)
  - module_video/edge: EdgeDeviceModel + capability_satisfies + CRUD(分页) + /heartbeat(upsert,脱敏) + settings + init_app backfill
3C Task 2/3 (编排/下发 + 事件接入) REMAIN.
3C Task 2: complete (commits 435eedf..444124f, review approved)
  - build_agent_task_config (spec §6) + EdgeAgentClient + EdgeOrchestrator(capability->compile->dispatch->start/stop) + edge_device_id + error_log; no-edge fallback to legacy worker
FOLLOWUP(3C t2): EdgeAgentClient.delete not wired (delete布控 leaves orphan on Agent); partial-failure orphan; local-agent skips capability check
3C Task 3 (事件接入) REMAIN.
3C Task 3: complete (commits 444124f..b39f929, review approved after MQTT topic/TLS/shutdown fixes)
  - normalize_edge_event + dedup + EdgeEventConsumer(lazy aiomqtt, 通配订阅, 退避重连, mqtts TLS); MQTT settings; init_app lifespan; service.py 快照引用
  - topic: publish {MQTT_TOPIC_PREFIX}/{edge_code}/camera/{camera_id}/detect, subscribe aistation/+/edge/+/camera/+/detect
PHASE 3C (edge-agent integration) 3 tasks complete. Remaining: wire Agent delete; Phase 3D 前端; final 3C review.
3C follow-up: delete布控同步删 Agent 侧任务 (commit 222f582). PHASE 3C COMPLETE.
VERIFIED backend pytest 252 passed.
3C legacy-worker hardening (旧 phase3c-inference.md Task1 补完): commit ab3659a
  - is_worker_alive 改 basename 精确匹配（修 test_inference_worker.py 子串误判）；scheduler start/stop/health 接通 pidfile 防重；_build_task_config 下发 schedule_json/interval_seconds/class_names；worker within_schedule/sensitivity_to_conf/label_name 生效
  - VERIFIED backend pytest 252 passed; ruff clean; test_inference_worker.py 8 passed
  - 未做（可选）: 旧 Task2 报警快照 HTTP 路由 + 规则匹配健壮（legacy worker 回退路径）
NEXT: Phase 3D 前端（边缘设备管理页/布控页设备选择与状态/告警快照预览）；磁盘暂无 3D plan，需先 brainstorming + writing-plans。

=== PHASE 3D: 云边可视化前端 ===
Spec: docs/superpowers/specs/2026-09-12-phase3d-cloud-edge-frontend-design.md (commit 770b87c)
Plan: docs/superpowers/plans/2026-09-12-phase3d-cloud-edge-frontend.md (commit 918a741)
3D baseline: ab3659a
3D Task 1: complete (旧 Task2 的快照路由部分) — 受控路由 /api/v1/video/detections/{path}（鉴权+防穿越）+ resolve_snapshot_url 归一化; tests test_snapshot_url.py(9)/test_snapshot_route.py(4)
3D Task 2: complete — AlarmRecordOutSchema.snapshot_url 计算字段 + pick_alarm_rule 规则匹配健壮化（修多规则 500）; tests test_alarm_rule_match.py(3)/test_alarm_snapshot_url.py(2)
3D Task 3: complete — 边缘设备管理页（edge.ts + EdgeCapabilityPanel + edge/index.vue + 15s轮询 + 详情抽屉 + _ensure_edge_page_menu 菜单补种）+ e2e/edge.spec.ts
3D Task 4: complete — LivePlayer overlay 插槽+getVideoElement；RoiEditor（实时预览+SVG 归一化多边形）；EdgeDeviceSelect（本机/纯云端哨兵 -1）；deploy 页设备选择/状态/error_log/ROI；e2e/deploy-edge-roi.spec.ts
3D Task 5: complete — SnapshotImage（鉴权 blob→objectURL、回收）+ 告警列表缩略图列 + 详情预览；e2e/alarm-snapshot.spec.ts
3D Task 6: complete (regression)
  - backend pytest 270 passed; ruff changed-files clean（全项目 FAST002 为 pre-existing）
  - frontend: 新增/改动文件 eslint+prettier clean；项目级 vue-tsc 有 16 条 pre-existing 错误（module_generator/monitor/system/task），与 3D 无关
  - Playwright e2e 全量 19 passed（含 3 条 3D 新用例）
  - 真机 Agent 端到端: **阻塞**（布控 Agent 属 ModelDeploy 仓库另一会话）；等价验证: mock 心跳 POST /video/edge/heartbeat → 设备 online + capabilities 可见 → 列表 → 删除清理成功
3D 提交区间: ab3659a..9911178
Minor(3D): 快照对象存储 key 与本地相对路径靠 is_file 区分（极小误判）；RoiEditor contain 坐标换算仅 E2E 区块级验证，真机未验；EdgeDeviceSelect 在能力拦截上只做展示不硬阻止；error_log 仅 tooltip 展示
PHASE 3D COMPLETE（6 tasks）。Remaining: 真机 Agent 端到端（依赖 ModelDeploy Agent 交付）。Next: Phase 4（端到端串联 + UI/UX 统一）。

=== PHASE 4: 端到端串联 + UI/UX 统一 ===
Spec: docs/superpowers/specs/2026-09-12-phase4-e2e-linking-ui-design.md (commit e16e7d4)
Plan: docs/superpowers/plans/2026-09-12-phase4-e2e-linking-ui.md (commit 1545124)
4 baseline: f4b9cab
4 Task 1: complete (commit ede7a8c) — 训练/评估列表 dataset_name/eval_dataset_name enrich（按页批量查 annotation_dataset）+ predict list 接通 name 搜索; test_train_dataset_name.py 3 passed
4 Task 2: complete (commit 43087ec) — task/detail handleEvaluate 跳 /train/eval?model_repo_id&autoCreate=1；eval 页 onMounted 自动开窗预填; e2e/train-to-eval.spec.ts
4 Task 3: complete (commit d0e1462) — repo 加「预测」按钮 + eval/detail「去预测」；predict 修 model_repo_id 用 repo_id；深链自动开窗; e2e/repo-to-predict.spec.ts
4 Task 4: complete (commit 7f228ba) — dataset 加「去训练」→ /train/task?dataset_id&autoCreate=1；训练页 dataset_id 预填开窗；数据集任务徽标改为直达工作台（旧 ?task_id= 由任务列表重定向兼容）; e2e/dataset-to-train.spec.ts
4 Task 5: complete (commit 90e6cbe) — base_model_id 控件/编辑回填/defaultHpPaddle 补 trainRatio；训练/评估列表与详情改用名称
4 Task 6: complete (commit c67b82e) — camera/record/alarm/algorithm/annotation 重复 toast 去除（algorithm 上传改 _silent 保留自定义文案）；repo 冗余条件 + task groupLabel 死代码；非标准 @media 标准化（GithubCorner/LockDialog/workplace）
4 Task 7: complete (commit d081727) — train eval/predict/deploy 创建弹窗统一为 EnhancedDialog（deploy 的 API Key 弹窗保持原生）
4 Task 8: complete (commit e6a6aab) — 深链自动开窗鲁棒性：predict 自动开窗仅依赖模型列表，数据集列表后台加载（修复累计请求下 dataset list 挂起导致不开窗）
  - VERIFIED backend pytest 273 passed; ruff schema/service clean（module_train/controller.py 91 FAST002 为 pre-existing）
  - frontend: e2e 全量 22 passed；vue-tsc 改动文件 0 错误（项目级 16 条 pre-existing）；eslint 改动文件 clean（annotation/task/record 残留为 pre-existing）
4 提交区间: f4b9cab..e6a6aab
Minor(4): 数据集任务徽标直达工作台（偏离原 spec 的"任务列表消费 task_id"，改为列表重定向兼容）；predict 深链自动开窗会清除 query，刷新不再弹；名称 enrich 对软删数据集回退 #id；E2E dismissTour 不用 Escape（避免误关自动弹窗）
PHASE 4 COMPLETE（8 tasks）。Next: Phase 5（非主链路半成品补全）→ Phase 6（全量回归验收 6 类型 × 2 框架）。

=== PHASE 5A: 非主链路半成品补全（P1-P6） ===
Spec: docs/superpowers/specs/2026-09-12-phase5a-halfdone-features-design.md (commit e98971e)
Plan: docs/superpowers/plans/2026-09-12-phase5a-halfdone-features.md (commit f1ae939)
5A baseline: 3f73187
5A Task 1: complete (commit 后) — P1 导出历史：export_dataset 写 annotation_dataset_export + 前端 ExportHistoryDrawer; test_export_history.py(1)
5A Task 2: complete — P4 部署详情/日志：getDeployDetail/Logs + DeployLogDrawer + deploy 页详情按钮; e2e/deploy-log.spec.ts
5A Task 3: complete — P2 定时训练：task 页「定时训练」Tab + SchedulePanel（vue3-cron-plus 可视化）+ schedule API; e2e/train-schedule.spec.ts
5A Task 4: complete — P3 数据清洗：CleanDrawer（健康检查/重复/异常）+ clean API + dataset 页入口; e2e/clean-drawer.spec.ts
5A Task 5: complete — P5 标注历史/回滚：rollback_annotation（append-only 新版本）+ POST /anno/image/{id}/rollback + AnnotationHistoryDrawer + 工作台历史按钮; test_annotation_rollback.py(1) + e2e/annotation-history.spec.ts
5A Task 6: complete — P6 仓库/版本 UI：repo 页改为仓库维度 + 版本抽屉；新增 createModelRepo/updateModelRepo/deleteModelRepos + 后端 PUT /model/repos/{id}（镜像名称/描述到最新版本）；修复编辑回归 + list_model_repos N+1 优化; e2e/repo-versions.spec.ts
  - VERIFIED backend pytest 275 passed；ruff 改动文件无新增（controller 91 FAST002 pre-existing）
  - frontend: vue-tsc 改动文件 0 错误；各特性 E2E 隔离运行均通过
  - 全量 E2E 波动（环境）：长时运行的后端出现 QueuePool limit（10+20）耗尽与 10s 客户端超时，导致个别用例（smoke/stats/clean-drawer/train-to-eval）在全量套件中间歇失败；等待连接池回收后单跑通过。非本次代码回归
5A 提交区间: f1ae939..b51dc54
Minor(5A): Task5 后端测试用服务层直接构造数据（行为由 E2E 覆盖）；仓库页搜索仍用 `name`；导出历史下载依赖 presigned URL 过期；cron 构建器渲染待人工确认
PHASE 5A COMPLETE（6 features）。Next: Phase 5B（P7 实时协作）→ Phase 6。

=== PHASE 5B: 实时协作（P7） ===
Spec: docs/superpowers/specs/2026-09-13-phase5b-realtime-collaboration-design.md (commit f5463e6)
Plan: docs/superpowers/plans/2026-09-13-phase5b-realtime-collaboration.md (commit f5463e6)
5B Task 1: complete (commit 65e6556) — WS 鉴权(query token via decode_access_token)+presence 在线列表+DB 锁(AnnotationService.lock_image)；parse_ws_user/presence_list；test_collaboration_ws.py(3)
5B Task 2: complete — frontend useCollab composable（连接/token/在线/焦点/远端标注tick/锁冲突tick/退避重连）
5B Task 3: complete (commit afb6669) — 工作台接入：在线指示、切图 focus、远端标注重载当前图、锁冲突 toast、卸载 close
5B Task 4: complete — e2e/collaboration.spec.ts（在线指示）；backend pytest 278 passed
5B 已知限制: 内存房间不支持多 worker（Redis 化后续）；last-write-wins 重载（无 CRDT）；远端光标仅广播未精确渲染
PHASE 5B COMPLETE。Next: Phase 6（全量回归验收 6 类型 × 2 框架）。

=== PHASE 6: 全量回归验收 ===
Plan: docs/superpowers/plans/2026-09-13-phase6-regression.md
Report: docs/superpowers/reports/2026-09-13-phase6-regression-report.md
6 自动化: backend pytest 278 passed；前端新增特性 E2E 逐项通过；vue-tsc 新增文件 0 错误
6 环境: Docker 29.5.3 + ultralytics/paddlex/rustfs/postgres/redis 镜像均在；后端 8001 + 前端 5180 运行中
6 全量 E2E: 受 dev 后端 QueuePool 耗尽/10s 超时影响间歇失败（环境负载，非代码回归）；单跑通过
6 矩阵真机: det/seg/obb/pose/cls 待人工；OCR det/rec 历史已验（SP2）
PROGRAM Phase 0-5 全部功能与自动化回归完成（含 3C/3D/4/5A/5B）。Phase 6 报告已出，真机矩阵待人工。

=== PERF: 全站下拉选项懒加载 ===
新增 frontend/src/composables/useOptions.ts（cachedOptions 短TTL缓存+并发去重 / useLazyOptions 懒加载）
改造页面（进页面请求数）：智能布控3->1、视频告警2->1(lazy tab)、视频联动2->1、视频布局2->1、录像2->1、训练任务4->2、训练详情评估/预测/部署去重、仓库/数据集/标注任务各1、统计2->1；启动 param/info 2->1
提交: 28d05f9 / useOptions / 4d1c977 / 6a644a4 / 8b75a55 / d722506
剩余合理的 page_size=100：训练评估/预测的模型名称映射、临时目录、相机分组（均属真实需要）

=== AI 管理 + 大模型应用 ===
Spec: docs/superpowers/specs/2026-09-13-ai-management-apps-design.md
Plan: docs/superpowers/plans/2026-09-13-ai-management-apps.md
后端: module_ai/provider(ai_models CRUD/脱敏/默认唯一/测试连接) + module_ai/report(ai_reports) + module_ai/assistant(16个工具 function-calling: 概览/数据集/标注任务/训练/模型/评估/预测/部署/相机/布控/告警/报告/导航/提议操作)；create_all 建表；_ensure_ai_menus 种子
前端: module_ai/model 模型配置页 + module_ai/report 报告页(markdown-it) + AiAssistant 优先走 /ai/assistant/chat（工具结果/导航/待确认操作/报告提示）
验证: backend pytest 283 passed（新增 5 用例）；vue-tsc 新增文件 0 错误；eslint clean；e2e/ai-model.spec.ts 通过
提交: 后端 provider/report/assistant + 前端页面与助手接入
已知限制: 助手无状态/非流式；工具只读；变更操作为前端二次确认后调用既有 API；需在 AI管理→模型配置 配置 OpenAI 兼容模型后助手才可用

=== AI 管理 v2（进行中，接续交接）===
Spec: docs/superpowers/specs/2026-09-13-ai-platform-v2-design.md
用户要求（务必遵守）:
  1) 前端设计用 frontend-design 技能，但**风格/明暗/大小/配色必须遵循 Element Plus 框架本身**（用 --el-* 变量），不得割裂；
  2) 完成后用**无头浏览器截图 + vision-recognition 技能做视觉分析**验收；
  3) 必须是**真流式**：思考(reasoning)/回复(delta)/工具(tool) 三类分片，前端逐步渲染；
  4) 不要想当然，按用户需求实现。
已完成:
  - A 阶段: providers 表/CRUD/拉取远端模型; ai_models 增 provider_id/usage/capabilities/context_window; get_runtime_model 解析 provider→model→env（usage NULL 视为通用）; 助手 SSE /ai/assistant/stream（reasoning+delta+tool+done）。
  - 控制台外壳: styles/ai-console.css（已改框架一致浅色）; /ai/overview 控制台; /ai/playground 运行台; ai_call_logs + /ai/overview/stats（日志写入需重启后端生效）。
  - 旧 AI 聊天/AI会话记忆 已 hidden 下线; AI 父菜单 redirect=/ai/overview。旧 Agno WS 链路弃用（module_ai/chat 保留代码不再展示）。
  - 相关提交: c773b7c / 58ba1ef / addc6f1 / a5b0f03 / 94064dc / 551c0cb。
待做（B-E，按此顺序）:
  B 提示词工作台(画布): 表 ai_prompts(name/category/blocks[JSONB 有序块]/variables/version/enabled); CRUD; 前端 /ai/prompt: 左块列表可拖拽、中间编辑、右变量识别与预览；菜单。
  C AI 应用 + 工具中心: 表 ai_apps(model_id/prompt_id/tools[JSONB]/output_format/input_schema/enabled/order); 表 ai_tools(kind builtin/http, method,url,headers,params_schema,enabled); 内置工具开关 + 自定义 HTTP 工具; 页面 /ai/app、/ai/tool；运行应用走 SSE（按 app 的 model/prompt/tools）。
  D 会话与日志页: 表 ai_sessions/ai_messages（按 app 续聊）; /ai/logs 页（ai_call_logs 列表/筛选）; 运行台支持选应用 + 会话历史。
  E 报告增强 + 全量测试: 报告模板; 后端 pytest（prompts/apps/tools/sessions/logs/SSE）; 前端 E2E（含截图+视觉验收）。
关键坑:
  - 后端 pytest 用持久化 SQLite(pytest_aistation.db)：改 schema 后需删除该文件再跑。
  - SSE 用 StreamingResponse(text/event-stream)，OperationLogRoute 不缓冲流；不要给流接口加会读 body 的中间件。
  - opencode 网关需 x-opencode-session（已自动注入）；模型 usage 为空的旧行按通用处理。
  - 旧聊天页 /ai/chat、记忆页 /ai/memory 已 hidden；如需彻底删除再评估。
验证:
  - 后端: cd backend && uv run pytest -q; uv run ruff check app/plugin/module_ai/
  - 前端: cd frontend && pnpm type-check; pnpm e2e（ai-model/ai-console 等）
  - 运行台: 问"我们有几个数据集？共多少张图？" 应见 思考/逐字回复/工具时间线。
下一步: 开新会话，从 B（提示词工作台）开始，逐项实现+测试+截图视觉验收。

--- AI v2 追加要求（用户强反馈，必须遵守）---
  5) 视觉必须与既有模块（如 系统设置/参数管理）**完全一致**：优先复用 Element Plus 组件原样
     （el-card / el-descriptions / el-table / el-form / el-tag / el-statistic 等），
     颜色/字体/字号/间距一律用 Element Plus 默认与 --el-* 变量；**不得自造主题化外壳**
     （当前 ai-console.css 的自定义面板/指标卡观感被用户否定，需按框架组件重做或直接去掉）。
     参考实现：frontend/src/views/module_system/param/index.vue 与 settings 分组。
  6) 与其新建一套，不如在**旧的 AI 助手页面骨架**上迭代（其布局/交互用户更认可），
     但数据链路换成新运行时+SSE 流式。旧页 /ai/chat 之前被 hidden，可按此方向恢复并改造。
  7) 登录偶发"请求超时"根因: dev 后端 DB 连接池(QueuePool)被长时运行/大量 e2e 打满;
     解决: 重启后端; 后续给 AI/整体可考虑调大 POOL_SIZE/MAX_OVERFLOW 或加连接回收。
