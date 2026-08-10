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
