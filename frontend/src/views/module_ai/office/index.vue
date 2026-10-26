<template>
  <div class="app-container ai-office-page">
    <div class="office-body">
      <!-- 左：花名册 -->
      <div class="office-roster">
        <div class="of-tabs">
          <button
            class="of-tab"
            :class="{ on: rosterTab === 'people' }"
            @click="setRosterTab('people')"
          >
            成员<span class="n">{{ onDuty }}</span>
          </button>
          <button
            class="of-tab"
            :class="{ on: rosterTab === 'tasks' }"
            @click="setRosterTab('tasks')"
          >
            任务<span class="n">{{ taskTotal }}</span>
          </button>
        </div>

        <template v-if="rosterTab === 'people'">
          <div class="of-stat">
            <span><b>{{ onDuty }}</b> 在岗</span>
            <span>入座 <b>{{ seated }}</b></span>
            <span v-if="overflow > 0" class="warn">{{ overflow }} 人未入座</span>
            <span
              v-if="pendingReview > 0"
              class="warn pending"
              :title="'动作写回 / 本体版本发布待审批，共 ' + pendingReview + ' 项'"
              @click="goApproval"
            >{{ pendingReview }} 待确认</span>
          </div>
          <input v-model="keyword" class="of-input" placeholder="搜索成员" />
          <div class="of-list">
            <div
              v-for="a in filtered"
              :key="a.id"
              class="m-row"
              :class="{ on: selected === a.id }"
              role="button"
              tabindex="0"
              :aria-pressed="selected === a.id"
              :title="`${a.name} · 点一下选中，并把镜头对准他`"
              @click="pick(a.id)"
              @keydown.enter.prevent="pick(a.id)"
            >
              <span class="m-av" :class="a.status">{{ (a.name || "?").slice(0, 1) }}</span>
              <div class="who">
                <div class="n">{{ a.name }}<span v-if="a.isLeader" class="lead">组长</span></div>
                <div class="s">{{ a.role || '未设置角色' }}</div>
              </div>
              <span class="st" :class="a.status">{{ statusWord(a.status) }}</span>
            </div>
            <div v-if="!filtered.length && !loading" class="of-empty">还没有智能体</div>
          </div>
          <div class="of-foot"><span class="link" @click="openSummary">今日简报 ›</span></div>
        </template>

        <template v-else>
          <div class="of-dstep">
            <button class="of-ico" title="前一天" @click="shiftTaskDate(-1)">‹</button>
            <span class="d">{{ taskDate || "最近 30 天" }}</span>
            <button class="of-ico" title="后一天" @click="shiftTaskDate(1)">›</button>
            <button class="of-mini" @click="goToday">今天</button>
          </div>
          <div class="of-filters">
            <button
              v-for="o in TASK_STATUS"
              :key="o.v"
              class="of-chip"
              :class="{ on: taskStatus === o.v }"
              @click="setTaskStatus(o.v)"
            >{{ o.label }}</button>
            <select v-model="taskAgent" class="of-select" @change="reloadTasks">
              <option value="">全部成员</option>
              <option v-for="a in agents" :key="a.id" :value="a.name">{{ a.name }}</option>
            </select>
          </div>
          <div class="of-list of-tl">
            <div
              v-for="t in tasks"
              :key="t.run_id"
              class="tl-item"
              :class="{ on: activeRun === t.run_id }"
              role="button"
              tabindex="0"
              @click="openRun(t.run_id)"
              @keydown.enter="openRun(t.run_id)"
            >
              <span class="tl-time">{{ t.started_time }}</span>
              <i class="tl-dot" :class="t.status" />
              <span class="tl-main">
                <span class="tl-p" :title="t.prompt">{{ t.prompt || "（无描述）" }}</span>
                <span class="tl-m">{{ t.steps }} 步 · {{ t.leader || "组长" }}</span>
                <span v-if="t.status === 'error' && t.error" class="tl-e" :title="t.error">
                  {{ t.error }}
                </span>
              </span>
              <button
                v-if="t.status === 'error' && t.prompt && !t.prompt.startsWith('定时任务：')"
                class="tl-retry"
                title="用同样的任务重跑一次"
                v-hasPerm="'module_ai:office:dispatch'"
                @click.stop="retryRun(t)"
              >重试</button>
            </div>
            <div v-if="!tasks.length && !taskLoading" class="of-empty">
              {{ taskFiltered ? "没有符合条件的派活" : taskDate ? "这一天没有派活" : "最近 30 天没有派活" }}
              <div v-if="!taskFiltered" class="of-samples">
                <span class="lbl">试试：</span>
                <button
                  v-for="(s, i) in SAMPLE_TASKS"
                  :key="i"
                  class="sample"
                  :title="s"
                  @click="usePrompt(s)"
                >{{ s }}</button>
              </div>
            </div>
          </div>
          <div class="of-pager" v-if="taskTotal > taskPageSize">
            <button class="of-ico" :disabled="taskPage <= 1" @click="loadTasks(taskPage - 1)">‹</button>
            <span><b>{{ taskPage }}</b> / {{ Math.max(1, Math.ceil(taskTotal / taskPageSize)) }}</span>
            <button
              class="of-ico"
              :disabled="taskPage * taskPageSize >= taskTotal"
              @click="loadTasks(taskPage + 1)"
            >›</button>
          </div>
        </template>
      </div>

      <!-- 右：3D 舞台 -->
      <el-card
        class="office-stage-card"
        shadow="never"
        v-loading="booting"
        element-loading-text="正在布置办公室…"
      >
        <div class="office-bar">
          <div class="of-bar">
            <span v-if="detail" class="of-picked" @click="clearPick">
              <i class="dot" :class="detail.status" />{{ detail.name }}<b>×</b>
            </span>
            <textarea
              v-if="detail"
              v-model="oneText"
              rows="1"
              class="of-input of-bar-input"
              placeholder="单独派活，回车发送，Shift+回车换行…"
              aria-label="单独派活的任务内容"
              @keydown.enter.exact.prevent="dispatchOne"
              @input="autoGrow"
            />
            <template v-else>
              <div v-if="recentPrompts.length" class="of-recent">
                <button
                  class="of-btn"
                  aria-label="最近派过的任务"
                  aria-haspopup="listbox"
                  :aria-expanded="recentOpen"
                  @click="recentOpen = !recentOpen"
                >最近 ▾</button>
                <i v-if="recentOpen" class="of-pop-mask" @click="recentOpen = false" />
                <div v-if="recentOpen" class="of-menu recent" role="listbox">
                  <button
                    v-for="(t, i) in recentPrompts"
                    :key="i"
                    role="option"
                    :aria-selected="false"
                    :title="t"
                    @click="usePrompt(t)"
                  >{{ t }}</button>
                </div>
              </div>
              <textarea
                ref="barInputRef"
                v-model="dispatchText"
                rows="1"
                class="of-input of-bar-input"
                :placeholder="`把任务交给 ${leaderName}（@某人 可单独派给他）…`"
                aria-label="交给组长的任务内容"
                @keydown.enter.exact.prevent="doDispatch"
                @input="onBarInput"
              />
            </template>
            <button
              v-if="detail && oneLoading"
              class="of-btn stop"
              @click="stopOne"
            >停止</button>
            <button
              v-else-if="detail"
              v-hasPerm="'module_ai:office:dispatch'"
              class="of-btn primary"
              :disabled="!oneText.trim() || oneLoading"
              :title="oneText.trim() ? '只派给这个人（Enter）' : '先写一句要他做什么'"
              @click="dispatchOne"
            >派给他</button>
            <button
              v-else-if="dispatching"
              class="of-btn stop"
              @click="stopDispatch"
            >停止</button>
            <button
              v-else
              v-hasPerm="'module_ai:office:dispatch'"
              class="of-btn primary"
              :disabled="!canSend"
              :title="canSend ? '交给组长协调（Enter）' : '先写一句要做什么'"
              @click="doDispatch"
            >派活</button>

            <div v-if="detail" class="of-look">
              <button class="of-btn" @click="lookOpen = !lookOpen">改形象</button>
              <i v-if="lookOpen" class="of-pop-mask" @click="lookOpen = false" />
              <div v-if="lookOpen" class="of-pop">
              <div class="ln">发型</div>
              <div class="sw">
                <button
                  v-for="st in HAIR_STYLES"
                  :key="st.key"
                  class="chip"
                  :class="{ on: lookDraft.style === st.key }"
                  @click="applyLook({ style: st.key })"
                >{{ st.label }}</button>
              </div>
              <div class="ln">衬衫</div>
              <div class="sw">
                <button
                  v-for="c in SHIRT_COLORS"
                  :key="c"
                  class="dot"
                  :style="{ background: c }"
                  @click="applyLook({ shirt: c })"
                />
              </div>
              <div class="ln">裤子</div>
              <div class="sw">
                <button
                  v-for="c in PANTS_COLORS"
                  :key="c"
                  class="dot"
                  :style="{ background: c }"
                  @click="applyLook({ pants: c })"
                />
              </div>
              <div class="ln">鞋子</div>
              <div class="sw">
                <button
                  v-for="c in SHOE_COLORS"
                  :key="c"
                  class="dot"
                  :style="{ background: c }"
                  @click="applyLook({ shoe: c })"
                />
              </div>
              <div class="ln">头发</div>
              <div class="sw">
                <button
                  v-for="c in HAIR_COLORS"
                  :key="c"
                  class="dot"
                  :style="{ background: c }"
                  @click="applyLook({ hair: c })"
                />
              </div>
              </div>
            </div>

            <span class="of-gap" />
            <div class="of-seg">
              <button :aria-pressed="floor === 1" @click="switchFloor(1)">1F</button>
              <button :aria-pressed="floor === 2" @click="switchFloor(2)">2F</button>
            </div>
            <button class="of-ico" :class="{ lit: partyOn }" title="叫人来蹦 / 清场" @click="toggleParty">🎉</button>
            <div class="of-more">
              <button class="of-ico" title="更多" @click="menuOpen = !menuOpen">⋯</button>
              <i v-if="menuOpen" class="of-pop-mask" @click="menuOpen = false" />
              <div v-if="menuOpen" class="of-menu">
                <button @click="doMenu('recent')">最近一轮执行</button>
                <button @click="doMenu('board')">清空白板</button>
                <button @click="doMenu('memory')">清空办公室记忆</button>
                <button @click="doMenu('refresh')">刷新在岗状态</button>
                <button @click="doMenu('guide')">重看引导</button>
                <button @click="doMenu('lowpower')">
                  省电模式：{{ lowPower ? "开（30fps）" : "关" }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 连接断了：留在页面上，别用会消失的 toast 糊过去 -->
        <div v-if="connLost" class="conn-lost">
          <span class="t">与后端的连接断了：{{ connLost.reason }}</span>
          <span class="d">
            这一轮可能已经中断；如果服务端其实跑完了，下面会自动把结论补回来。
          </span>
          <span class="spacer" />
          <button v-if="connLost.retry" class="of-btn" @click="retryAfterLost">
            重试这一轮
          </button>
          <button class="of-btn" @click="connLost = null">知道了</button>
        </div>

        <!-- 今日统计：常驻一条，点开看完整简报 -->
        <div class="of-stats" v-if="summary.runs && summary.runs.total">
          <span class="it">今日派活 <b>{{ summary.runs.total }}</b></span>
          <span class="it" :class="{ bad: summary.runs.errors }">
            失败 <b>{{ summary.runs.errors }}</b>
            <template v-if="summary.runs.errors">（{{ summary.runs.error_rate }}%）</template>
          </span>
          <span class="it">平均 <b>{{ fmtMs(summary.runs.avg_ms) }}</b></span>
          <span class="it">最近 <b>{{ summary.runs.last_time || "—" }}</b></span>
          <span class="spacer" />
          <span class="more" @click="openSummary">今日简报 ›</span>
        </div>

        <div class="stage" ref="stageRef" :class="{ night: isNight }">
          <div class="plates" ref="platesRef" />

          <!-- 镜头预设：全景 / 跟随执行者 / 白板 / 大屏 -->
          <div class="cam-presets" role="group" aria-label="镜头预设">
            <button
              v-for="m in CAM_MODES"
              :key="m.v"
              :class="{ on: camMode === m.v }"
              :aria-pressed="camMode === m.v"
              :title="m.tip"
              @click="setCamMode(m.v)"
            >{{ m.label }}</button>
          </div>

          <!-- 首次引导：只出现一次，菜单里可重看 -->
          <div v-if="guideOpen" class="guide-mask" role="dialog" aria-modal="true" aria-label="办公室上手指引">
            <div class="guide-card">
              <div class="g-head">
                <span class="g-cap">第 {{ guideStep + 1 }} / {{ GUIDE_STEPS.length }} 步</span>
                <span class="g-t">{{ GUIDE_STEPS[guideStep].t }}</span>
              </div>
              <div class="g-d">{{ GUIDE_STEPS[guideStep].d }}</div>
              <div class="g-foot">
                <span class="dots">
                  <i
                    v-for="(s, i) in GUIDE_STEPS"
                    :key="i"
                    :class="{ on: i === guideStep }"
                    :title="s.t"
                  />
                </span>
                <span class="spacer" />
                <button class="of-btn" @click="closeGuide">跳过</button>
                <button class="of-btn primary" @click="nextGuide">
                  {{ guideStep >= GUIDE_STEPS.length - 1 ? "知道了" : "下一步" }}
                </button>
              </div>
            </div>
          </div>
          <div class="people-hint" v-if="peopleHint && !webglError">
            <i class="dot" />同事正在入座…
          </div>
          <div class="gl-lost" v-if="glLost && !webglError">
            <div class="t">3D 场景被系统回收了</div>
            <div class="d">
              {{
                glStuck
                  ? "自动恢复没有成功，可以直接重建场景（不会刷新页面，列表和执行过程都还在）。"
                  : "电脑休眠、切换显卡或驱动重置时会出现，正在尝试自动恢复…"
              }}
            </div>
            <button class="of-btn primary" :disabled="glReloading" @click="rebuildOffice">
              {{ glReloading ? "重建中…" : "立即重建场景" }}
            </button>
          </div>
          <div
            v-if="cronBanner"
            class="cron-hint"
            :class="cronBanner.status"
            :title="`${cronBanner.name} · 点开看这一轮的执行过程`"
            @click="openRun(cronBanner.runId)"
          >
            <span class="bell">⏰</span>
            <span class="nm">{{ cronBanner.name }}</span>
            <span v-if="cronBanner.status === 'running'" class="st live">执行中…</span>
            <span v-else-if="cronBanner.status === 'error'" class="st bad">执行失败</span>
            <span v-else class="st good">
              完成 · {{ Math.max(1, Math.round((cronBanner.ms || 0) / 1000)) }} 秒
            </span>
            <span v-if="cronBanner.agent" class="who">{{ cronBanner.agent }}</span>
          </div>
          <div class="wrap-hint" v-if="wrapHint">
            <i class="dot" />{{ wrapHint }}
          </div>
          <div class="of-trace" v-if="steps.length">
            <div class="of-thead">
              <span class="t">执行过程</span>
              <i v-if="oneLoading || dispatching" class="live" />
              <span v-if="hasMemory" class="mem">带上下文</span>
              <span class="spacer" />
              <button
                v-if="steps.some((s) => s.kind === 'tool' || s.kind === 'summary')"
                class="of-linkbtn"
                :aria-label="allOpen ? '收起全部步骤' : '展开全部步骤'"
                @click="toggleAllSteps"
              >{{ allOpen ? "收起全部" : "展开全部" }}</button>
              <span class="c">{{ steps.length }} 步</span>
            </div>
            <div class="of-tbody" ref="stepsBodyRef" @scroll.passive="onStepsScroll">
              <div class="of-root" v-if="tree.plan">
                <i class="bul" />
                <div>
                  <div class="ttl">
                    接活 · {{ tree.plan.actor || "组长" }}
                    <span v-if="tree.plan.time" class="tm">{{ tree.plan.time }}</span>
                  </div>
                  <div class="ask">{{ plainText(tree.plan.detail || "") }}</div>
                </div>
              </div>

              <div
                class="of-branch"
                v-for="(b, i) in tree.branches"
                :key="i"
                :style="{ animationDelay: Math.min(i, 6) * 45 + 'ms' }"
              >
                <div class="bhead">
                  <i class="who-dot" :style="{ background: personColor(b.agent) }" />
                  <span class="n">{{ b.agent || "组长" }}</span>
                  <span v-if="b.tools.length" class="cnt">{{ b.tools.length }} 次工具</span>
                  <span v-if="b.delegate?.time" class="tm">
                    {{ b.delegate.time
                    }}<template v-if="b.reply?.time || b.delegate?.replyTime">
                      → {{ b.reply?.time || b.delegate?.replyTime }}</template>
                  </span>
                </div>
                <div
                  class="tool"
                  v-for="(t, k) in b.tools"
                  :key="k"
                  :class="{ open: t.open }"
                  @click="t.open = !t.open"
                >
                  <span class="k">{{ toolName(t) }}</span>
                  <span class="a">{{ stepView(t).text }}</span>
                  <span v-if="briefResult(t)" class="r">{{ briefResult(t) }}</span>
                  <pre v-if="t.open && t.result" class="of-res">{{ plainText(t.result) }}</pre>
                </div>
                <div v-if="b.reply || b.delegate?.result" class="say">
                  {{ plainText(b.reply?.detail || b.delegate?.result || "") }}
                </div>
              </div>

              <div v-if="tree.summary" class="of-sum" :class="{ err: tree.summary.kind === 'error' }">
                <div class="h">
                  <i class="who-dot" :style="{ background: personColor(tree.summary.actor || '') }" />
                  {{ tree.summary.kind === "error" ? "失败" : "汇总" }} ·
                  {{ tree.summary.actor || "组长" }}
                  <span class="spacer" />
                  <button
                    class="of-linkbtn"
                    :aria-label="tree.summary.kind === 'error' ? '复制错误信息' : '复制结论'"
                    @click.stop="
                      copyText(
                        tree.summary.detail || '',
                        tree.summary.kind === 'error' ? '已复制错误信息' : '已复制结论'
                      )
                    "
                  >{{ tree.summary.kind === "error" ? "复制错误" : "复制结论" }}</button>
                </div>
                <div class="x">{{ plainText(tree.summary.detail || "") }}</div>
              </div>
            </div>
            <button
              v-if="showJumpLatest"
              class="of-jump"
              aria-label="回到最新步骤"
              @click="jumpLatest"
            >回到最新 ↓</button>
            <div class="of-tfoot">
              <span class="lg"><i class="dot" />完成</span>
              <span class="lg"><i class="dot wait" />待确认</span>
              <span class="lg"><i class="dot err" />失败</span>
              <span class="sp" />
              <span>拖动旋转 · 滚轮缩放</span>
            </div>
          </div>

          <div class="stage-empty" v-if="!booting && !agents.length">
            <div class="of-empty-block">
              <div class="t">办公室里还没有智能体</div>
              <button class="of-btn" @click="openWorkspace">去工作台新建</button>
            </div>
          </div>
          <div class="stage-empty" v-else-if="webglError">
            <div class="of-empty-block">
              <div class="t">3D 场景没能加载</div>
              <div class="d">
                当前浏览器或显卡不支持 WebGL（{{ webglError }}）。<br />
                右侧「执行过程」照常可用，派活、任务列表都不受影响。
              </div>
            </div>
          </div>

        </div>

        <!-- 任务播报：一行滚动，展开看最近 30 条（只在前端内存，不额外请求） -->
        <div class="cast-bar" :class="{ open: castOpen, bad: castBad }">
          <span class="cap"><i class="live" />播报</span>
          <span class="one" :class="{ bad: castLast?.bad }" :title="castLast?.text || ''">
            <template v-if="castLast">
              <i class="g">{{ castGlyph(castLast?.kind ?? "info") }}</i>
              <em>{{ castLast.t }}</em>
              {{ castLast.text }}
            </template>
            <template v-else>还没有动静 —— 派个活，这里会实时播报谁在做什么</template>
          </span>
          <span v-if="castBad" class="bad-dot" title="有失败或断线记录" />
          <button
            class="of-linkbtn"
            :aria-expanded="castOpen"
            aria-label="展开或收起任务播报"
            @click="toggleCast"
          >{{ castOpen ? "收起" : `展开（${casts.length}）` }}</button>
          <div v-if="castOpen" class="cast-list" role="log" aria-live="polite">
            <div v-for="c in castDesc" :key="c.id" class="c" :class="{ bad: c.bad }">
              <em>{{ c.t }}</em>
              <i class="g">{{ castGlyph(c.kind) }}</i>
              <span class="x">{{ c.text }}</span>
            </div>
            <div v-if="!casts.length" class="empty">还没有播报</div>
          </div>
        </div>

        <div class="brief-bar" v-if="briefText">
          <span class="cap"><i class="dot" />组长结论</span>
          <span class="txt" :title="resultText">{{ briefText }}</span>
          <el-button link type="primary" size="small" @click="showResultOnScreen">看全文</el-button>
          <el-button
            link
            size="small"
            @click="copyText(resultText || briefText, '已复制结论')"
          >复制</el-button>
          <el-button link size="small" @click="briefText = ''">收起</el-button>
        </div>
        <div class="run-strip">
          <span class="cap"><i class="live" />最近执行</span>
          <span
            v-for="t in recentTasks"
            :key="t.run_id"
            class="it clickable"
            :class="{ on: activeRun === t.run_id }"
            :title="t.prompt"
            @click="openRun(t.run_id)"
          >
            <em>{{ t.leader || "组长" }}</em>
            <span class="u">{{ t.steps }} 步</span>
            <i class="res" :class="t.status === 'error' ? 'error' : ''" />
            <time>{{ t.started_time }}</time>
          </span>
          <span v-if="!recentTasks.length" class="it muted">暂无执行记录</span>
          <span class="spacer" />
          <span class="more" @click="goLogs">日志 ›</span>
        </div>
        <div class="stage-foot">
          <span class="legend"><i class="d idle" />在岗</span>
          <span class="legend"><i class="d busy" />工作中</span>
          <span class="legend"><i class="d wait" />等你确认</span>
          <span class="spacer" />
          <span class="tip">拖动旋转 · 滚轮缩放 · 人多了自动收起名牌</span>
        </div>
      </el-card>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown } from "@element-plus/icons-vue";
import {
  getAiAgentDetail,
  getAiAgentOffice,
  getOfficeSummary,
  getOfficeSteps,
  getOfficeRuns,
  clearOfficeMemory,
  streamOfficeDispatch,
  dispatchOfficeAgent
} from "@/api/module_ai/agent";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiLogRecent, getAiToolCalls } from "@/api/module_ai/logs";
import { getApprovalCenter } from "@/api/module_ai/query";
// @ts-ignore 纯 JS 场景模块（three 无类型声明）
import { createOffice } from "./office3d.js";
import { castGlyph, castHandoff, hasBad, makeCast, pushCast, type CastItem } from "./broadcast";

interface OfficeAgent {
  id: number;
  name: string;
  role: string;
  status: "idle" | "busy" | "wait" | "error";
  task?: string;
  last_active?: string | null;
  isLeader?: boolean;
}

const router = useRouter();
const stageRef = ref<HTMLElement>();
const platesRef = ref<HTMLElement>();
const agents = ref<OfficeAgent[]>([]);
const runs = ref<any[]>([]);
const loading = ref(false);
const booting = ref(true);
/** 人物是否已经落座（角色模型加载完才 setAgents，之前舞台是空房间） */
const peopleReady = ref(false);
/** 提示延迟 0.7 秒再出现：机器快时人物瞬间就位，别闪一下文字 */
const peopleHint = ref(false);
let peopleHintTimer: number | null = null;
/** 3D 初始化失败的原因（WebGL 不可用等）；为空表示正常 */
const webglError = ref("");const keyword = ref("");
const selected = ref<number | null>(null);
const seated = ref(0);

/* ================= 首次引导（只出现一次，菜单里可重看） ================= */
const GUIDE_KEY = "office.guide.v1";
const guideOpen = ref(false);
const guideStep = ref(0);
const GUIDE_STEPS = [
  {
    t: "选人 = 单独派活",
    d: "点左上名单里的某位同事（或在 3D 里点他），派活框会切成「派给他」，任务只交给这一个人。"
  },
  {
    t: "不选人 = 交给组长",
    d: "直接在顶部输入框写任务，组长会自己拆活、分给合适的同事，并把结果汇总回来。"
  },
  {
    t: "右侧看执行过程",
    d: "接活、调了哪些工具、谁回了什么、最后结论，都在右侧「执行过程」里，点开每一步看参数和返回。"
  }
];
function openGuide() {
  guideStep.value = 0;
  guideOpen.value = true;
}
function closeGuide() {
  guideOpen.value = false;
  try {
    localStorage.setItem(GUIDE_KEY, "1");
  } catch {
    /* 隐私模式写不了，下次还会出现，可接受 */
  }
}
function nextGuide() {
  if (guideStep.value >= GUIDE_STEPS.length - 1) closeGuide();
  else guideStep.value += 1;
}

/* ================= 任务播报（底部一条，可展开最近 30 条） ================= */
const CAST_KEY = "office.cast.open";
const casts = ref<CastItem[]>([]);
const castOpen = ref(false);
const castBad = computed(() => hasBad(casts.value));
const castLast = computed<CastItem | null>(() => casts.value[casts.value.length - 1] || null);
function addCast(kind: CastItem["kind"], text: string, bad = false) {
  if (!text) return;
  casts.value = pushCast(casts.value, makeCast(kind, text, { bad }));
}
function toggleCast() {
  castOpen.value = !castOpen.value;
  try {
    localStorage.setItem(CAST_KEY, castOpen.value ? "1" : "0");
  } catch {
    /* 忽略 */
  }
}

/* ================= 镜头：全景 / 跟随执行者 / 白板 / 大屏 ================= */
type CamMode = "overview" | "follow" | "board" | "screen";
const camMode = ref<CamMode>("overview");
/** 跟随模式限流：3 秒内不重复推镜头，否则多成员并行时画面乱跳 */
const FOLLOW_GAP_MS = 3000;
let lastFollowAt = 0;
function setCamMode(m: CamMode) {
  camMode.value = m;
  if (m === "follow") {
    const who = lastActor.value;
    if (who) focusWho(who);
    return;
  }
  office?.cameraPreset?.(m);
}
function focusWho(name?: string | null) {
  if (!name) return false;
  const ok = office?.focusAgent?.(name, 2.2);
  if (!ok) ElMessage.info(`没在场景里找到「${name}」的座位`);
  return !!ok;
}
/** 当前该跟随谁：最近一条带 actor 的步骤 */
const lastActor = computed(() => {
  for (let i = steps.value.length - 1; i >= 0; i--) {
    const a = steps.value[i].actor;
    if (a) return a;
  }
  return "";
});
function followIfNeeded(actor?: string) {
  if (camMode.value !== "follow" || !actor) return;
  const now = Date.now();
  if (now - lastFollowAt < FOLLOW_GAP_MS) return;
  lastFollowAt = now;
  focusWho(actor);
}

/* ================= 最近任务：一键填回输入框（不自动发送） ================= */
const RECENT_KEY = "office.recentPrompts";
const recentPrompts = ref<string[]>([]);
function rememberPrompt(t: string) {
  const s = String(t || "").trim();
  if (!s) return;
  recentPrompts.value = [s, ...recentPrompts.value.filter((x) => x !== s)].slice(0, 5);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recentPrompts.value));
  } catch {
    /* 忽略 */
  }
}
function usePrompt(t: string) {
  /* 示例/最近任务是「交给组长」的写法：如果当前选中了某个人，先退出单干模式，
     否则填进 dispatchText 也看不见（工具栏显示的是单干输入框） */
  if (detail.value) clearPick();
  dispatchText.value = t;
  recentOpen.value = false;
  nextTick(() => {
    const el = barInputRef.value;
    if (el) {
      el.focus();
      autoGrow();
    }
  });
}

/* ================= 派活输入：自适应高度 + 空内容禁用 + @成员 ================= */
const barInputRef = ref<HTMLTextAreaElement | null>(null);
const recentOpen = ref(false);
const canSend = computed(() => !!dispatchText.value.trim() && !dispatching.value);
function autoGrow() {
  const el = barInputRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 92)}px`;
}
/** 输入 @名字 + 空格：自动切到单干（匹配不到就保持原样） */
function onBarInput() {
  autoGrow();
  const m = /^@(\S+)\s+([\s\S]*)$/.exec(dispatchText.value);
  if (!m) return;
  const who = agents.value.find((a) => a.name === m[1]);
  if (!who) return;
  /* 把剩下的内容挪到单干输入框里：切过去之后用户还能看见自己写的字 */
  oneText.value = m[2];
  dispatchText.value = "";
  if (selected.value !== who.id) pick(who.id);
  nextTick(autoGrow);
}

/* ================= 执行过程：粘底滚动 + 展开/收起全部 ================= */
const stickBottom = ref(true);
const showJumpLatest = ref(false);
function onStepsScroll() {
  const el = stepsBodyRef.value;
  if (!el) return;
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
  stickBottom.value = gap < 40;
  showJumpLatest.value = !stickBottom.value && steps.value.length > 0;
}
function jumpLatest() {
  const el = stepsBodyRef.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
  stickBottom.value = true;
  showJumpLatest.value = false;
}
/** 面板头「展开/收起全部」：工具步骤的参数与返回一起开合 */
const allOpen = ref(false);
function toggleAllSteps() {
  allOpen.value = !allOpen.value;
  steps.value = steps.value.map((s) =>
    s.kind === "tool" || s.kind === "summary" ? { ...s, open: allOpen.value } : s
  );
  /* 展开后内容变长/变短，粘底状态要重算（否则「回到最新」要等下一次滚动才出现） */
  nextTick(onStepsScroll);
}

/** 播报列表倒序（最新在上），模板里直接用 */
const castDesc = computed(() => casts.value.slice().reverse());

/** 镜头预设按钮 */
const CAM_MODES: { v: CamMode; label: string; tip: string }[] = [
  { v: "overview", label: "全景", tip: "回到默认全景视角" },
  { v: "follow", label: "跟随", tip: "有新步骤时把镜头推给当前执行者（3 秒一次，避免乱跳）" },
  { v: "board", label: "白板", tip: "看白板上的分工与打勾" },
  { v: "screen", label: "大屏", tip: "看大屏上的结论" }
];

/** 空态示例任务：点一下只填入输入框，不自动发送 */
const SAMPLE_TASKS = [
  "让团队统计一下数据集总数和标注任务数，汇总成两行",
  "查一下最近一周失败的任务，说明原因",
  "帮我写一段本周数据治理工作的周报要点"
];

/* ================= 复制结论 / 错误 ================= */
async function copyText(text: string, okMsg = "已复制") {
  const s = String(text || "").trim();
  if (!s) {
    ElMessage.info("没有可复制的内容");
    return;
  }
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(s);
    } else {
      /* http 环境（内网 IP）没有 clipboard API：退回到隐藏 textarea */
      const ta = document.createElement("textarea");
      ta.value = s;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    ElMessage.success(okMsg);
  } catch {
    ElMessage.warning("复制失败，请手动选中文本");
  }
}

/** 左栏页签：成员 / 任务 */
/** 页签也记一下：上次看的是任务列表，回来还看任务列表 */
function setRosterTab(v: "people" | "tasks") {
  rosterTab.value = v;
  try {
    localStorage.setItem("ai_office_tab", v);
  } catch {
    /* 隐私模式忽略 */
  }
}
const rosterTab = ref<"people" | "tasks">(
  ((): "people" | "tasks" => {
    try {
      return localStorage.getItem("ai_office_tab") === "tasks" ? "tasks" : "people";
    } catch {
      return "people";
    }
  })()
);
/** 今天的派活列表（一次派活 = 一条） */
const tasks = ref<any[]>([]);
const taskLoading = ref(false);
/** 当前面板里展示的是哪一次 run（列表高亮用） */
const activeRun = ref<string | null>(null);
/** 任务列表：日期筛选（空 = 最近 30 天）+ 分页 */
function todayStr(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
const taskDate = ref<string | null>(todayStr());
const taskPage = ref(1);
const taskPageSize = 10;
const taskTotal = ref(0);
/** 筛选：状态 / 参与成员 */
const taskStatus = ref<"" | "ok" | "error" | "running">("");
const taskAgent = ref<string>("");
const taskFiltered = computed(() => !!taskStatus.value || !!taskAgent.value);
/** 底部流水条：今天最近 3 次（不受上面筛选影响） */
const recentTasks = ref<any[]>([]);

/** 状态筛选选项 */
const TASK_STATUS: { v: "" | "ok" | "error" | "running"; label: string }[] = [
  { v: "", label: "全部" },
  { v: "ok", label: "完成" },
  { v: "error", label: "失败" },
  { v: "running", label: "进行中" }
];

function fmtDay(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 日期步进：空白时从今天算 */
function shiftTaskDate(delta: number) {
  const base = taskDate.value ? new Date(taskDate.value + "T00:00:00") : new Date();
  base.setDate(base.getDate() + delta);
  taskDate.value = fmtDay(base);
  reloadTasks();
}

function goToday() {
  taskDate.value = todayStr();
  reloadTasks();
}

function setTaskStatus(v: "" | "ok" | "error" | "running") {
  taskStatus.value = v;
  reloadTasks();
}

/* 白板：最近 5 条结论，刷新后还在 */
const BOARD_KEY = "office:board";
const boardNotes = ref<string[]>([]);

function loadBoard() {
  try {
    const raw = localStorage.getItem(BOARD_KEY);
    if (raw) boardNotes.value = JSON.parse(raw) || [];
  } catch {
    boardNotes.value = [];
  }
  office?.writeBoard?.(boardNotes.value);
}

function pushBoard(text: string) {
  const line = (text || "").replace(/\s+/g, " ").trim().slice(0, 60);
  if (!line) return;
  boardNotes.value = [line, ...boardNotes.value.filter((x) => x !== line)].slice(0, 5);
  try {
    localStorage.setItem(BOARD_KEY, JSON.stringify(boardNotes.value));
  } catch {
    /* 存不下就算了 */
  }
  office?.writeBoard?.(boardNotes.value);
}

/* 顶栏「改形象」浮层 */
const lookOpen = ref(false);
/** 「⋯」菜单 & 蹦迪状态 */
const menuOpen = ref(false);
const partyOn = ref(false);
/* 省电模式：30fps + 关 SSAO（实测 chrome 进程 CPU 118% → 66%），默认关，记在本地 */
const LOWPOWER_KEY = "office.lowPower";
const lowPower = ref(false);
function applyQuality() {
  office?.setQuality?.(lowPower.value ? "low" : "high");
}
function toggleLowPower() {
  lowPower.value = !lowPower.value;
  try {
    localStorage.setItem(LOWPOWER_KEY, lowPower.value ? "1" : "0");
  } catch {
    /* 隐私模式忽略 */
  }
  applyQuality();
  ElMessage.success(lowPower.value ? "已开省电模式（30fps，画质略降）" : "已关省电模式（60fps）");
}

function refreshPartyState() {
  partyOn.value = (office?.partyCount?.() || 0) > 0;
}

/** 一键叫人蹦 / 一键清场 */
function toggleParty() {
  refreshPartyState();
  if (partyOn.value) {
    office?.stopParty?.();
    partyOn.value = false;
    ElMessage.info("已清场");
    return;
  }
  const n = office?.party?.(3) || 0;
  if (!n) {
    ElMessage.info("现在没有待命的人，等他们空下来再叫");
    return;
  }
  partyOn.value = true;
  ElMessage.success(`叫了 ${n} 个人去蹦迪`);
}

function doMenu(k: string) {
  menuOpen.value = false;
  if (k === "recent") replayOrOpen();
  else if (k === "refresh") refreshAll();
  else if (k === "board") void clearBoard();
  else if (k === "memory") void clearMemory();
  else if (k === "guide") openGuide();
  else if (k === "lowpower") toggleLowPower();
}

/** 清空白板（最近 5 条结论） */
async function clearBoard() {
  try {
    await ElMessageBox.confirm("白板上「最近结论」的 5 条会被清空，且不可恢复。", "清空白板", {
      confirmButtonText: "清空",
      cancelButtonText: "取消",
      type: "warning"
    });
  } catch {
    return;
  }
  boardNotes.value = [];
  try {
    localStorage.removeItem(BOARD_KEY);
  } catch {
    /* 忽略 */
  }
  office?.writeBoard?.([]);
  ElMessage.success("白板已清空");
}

/** 清空上下文记忆（前几轮问答） */
async function clearMemory() {
  try {
    await ElMessageBox.confirm(
      "接下来派活时不再自动带上前面几轮的结论（已有的执行步骤不受影响）。",
      "清空办公室记忆",
      { confirmButtonText: "清空", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await clearOfficeMemory();
    hasMemory.value = false;
    ElMessage.success("已清空上下文记忆");
  } catch (e: any) {
    ElMessage.error(e?.message || "清空失败");
  }
}

/** 顶栏 ↺：有本地帧就重放，没有就把最近一次执行摊开 */
function replayOrOpen() {
  if (canReplay.value) replayLast();
  else openRun();
}

/** 顶栏 ⟳：在岗状态 + 任务列表 + 流水条一起刷 */
function refreshAll() {
  load(true);
  loadTasks(taskPage.value);
  loadRecent();
}

/** 成员状态用词 */
function statusWord(st: string): string {
  return st === "error" ? "执行失败" : st === "busy" ? "工作中" : st === "wait" ? "等你确认" : "待命";
}
/** 待你确认（审批中心总数：动作写回 + 本体发布） */
const pendingReview = ref(0);

/* 派活给组长 */
const dispatchText = ref("");
const dispatching = ref(false);
/** 当前这一轮的中断器（停止 / 超时都走它） */
const dispatchAbort = ref<AbortController | null>(null);
/** 一轮最多跑多久，超时自动停 */
const DISPATCH_TIMEOUT_MS = 5 * 60 * 1000;
/** 收尾表演进行中的提示（组长走向白板） */
const wrapHint = ref("");
/** 结论摘要（贴在舞台上，避免弹窗把整场戏遮住） */
const briefText = ref("");
/* 回放：记住最近一轮的"派活帧"，可以原样重演（刷新页面也还在） */
type RunFrame = { t: number; type: string; from?: string; to?: string; text?: string; task?: string };
type RunRec = { at: string; leader?: string; members: string[]; summary: string; frames: RunFrame[] };
const lastRun = ref<RunRec | null>(null);
const replaying = ref(false);
const canReplay = computed(() => !!lastRun.value?.frames?.length);
/** 「更多」菜单 */
function onMore(cmd: string) {
  if (cmd === "replay") {
    // 本地有这轮的气泡帧就动画重放；没有就直接摊开最近一次落库的执行记录
    if (canReplay.value) replayLast();
    else openRun();
  }
  else if (cmd === "refresh") {
    load(true);
    loadTasks(taskPage.value);
    loadRecent();
  }
}

/* ---------- 执行过程（对话式时间线） ---------- */
type Step = {
  kind: string;
  title: string;
  actor?: string;
  detail?: string;
  result?: string;
  time?: string;
  /** 组员回话的时间（面板上显示「派活 → 回话」） */
  replyTime?: string;
  open?: boolean;
};

/** 执行过程按「组长接活 → 各支线 → 汇总」组织，不再是一条聊天流 */
type Branch = { agent: string; tools: Step[]; reply?: Step; delegate?: Step };

const tree = computed(() => {
  const all = steps.value;
  const plan = all.find((x) => x.kind === "plan");
  const summary =
    [...all].reverse().find((x) => x.kind === "summary" || x.kind === "error") || null;
  const branches: Branch[] = [];
  let cur: Branch | null = null;

  for (const st of all) {
    if (st.kind === "tool") {
      const target = toolTarget(st);
      if (target) {
        // 委派：开一条新支线（把这一步也存下：组员没调工具时，回话会被 foldRows 合并进它的 result）
        cur = { agent: target, tools: [], delegate: st };
        branches.push(cur);
        continue;
      }
      /* 普通工具：必须挂到「真正调用它的那个人」的支线上。
         之前是挂到"最近开的那条支线"，结果 A 派的活、B 调的工具会算到 A 头上
         （实测：问数助手调的 list_datasets 被算成企业协作助理的工具）。 */
      const who = (st.actor || "").trim();
      let owner = who ? branches.find((x) => x.agent === who) : null;
      if (!owner) {
        owner = { agent: who || "组长", tools: [] };
        branches.push(owner);
        cur = owner;
      }
      owner.tools.push(st);
    } else if (st.kind === "reply") {
      const who = (st.actor || st.title.replace(" 回话", "")).trim();
      const b = [...branches].reverse().find((x) => x.agent === who) || cur;
      if (b) b.reply = st;
      else branches.push({ agent: who, tools: [], reply: st });
    }
  }
  return { plan, branches, summary };
});

/** 工具返回压成一小截，挂在工具名后面（点开才看全文） */
function briefResult(st: Step): string {
  const raw = (st.result || "").replace(/\s+/g, " ").trim();
  if (!raw) return "";
  const m = raw.match(/(?:count|total|dataset_count|task_count|image_count)\D{0,6}(\d+)/i);
  if (m) return m[1];
  const n = raw.match(/\b(\d{1,6})\b/);
  if (n && raw.length > 24) return n[1];
  return raw.length > 18 ? raw.slice(0, 18) + "…" : raw;
}

/** 每个人一个固定颜色（名字哈希）——区分"这是谁干的"，与"哪类步骤"无关 */
function personColor(name: string): string {
  if (!name) return "var(--el-color-primary)";
  let h = 0;
  for (const ch of name) h = (h * 31 + (ch.codePointAt(0) || 0)) % 360;
  return `hsl(${h} 58% 50%)`;
}

/** 从 detail 的 JSON 里取工具名 / 目标成员 */
function toolName(s: Step): string {
  try {
    const j = JSON.parse(s.detail || "{}");
    return String(j.tool || "tool");
  } catch {
    return "tool";
  }
}
function toolTarget(s: Step): string {
  try {
    const j = JSON.parse(s.detail || "{}");
    return String((j.args && j.args.member) || "");
  } catch {
    return "";
  }
}
const steps = ref<Step[]>([]);
/** 这一轮是否带上了前几次派活的结论（追问能接上） */
const hasMemory = ref(false);
const stepsBodyRef = ref<HTMLElement | null>(null);

/* 新步骤进来时自动滚到底：看的是"最新发生了什么"，不是从头读。
   但用户手动上滑看历史时不能再把他拽回来（粘底），只提示「回到最新」。 */
watch(
  () => steps.value.length,
  async () => {
    await nextTick();
    const el = stepsBodyRef.value;
    if (!el) return;
    if (stickBottom.value) {
      el.scrollTop = el.scrollHeight;
      showJumpLatest.value = false;
    } else {
      showJumpLatest.value = true;
    }
  }
);

const KIND_LABEL: Record<string, string> = {
  plan: "规划",
  tool: "工具",
  reply: "回话",
  summary: "汇总",
  error: "失败"
};
function kindLabel(k: string) {
  return KIND_LABEL[k] || k;
}

/** 工具步骤的专属渲染：不同工具显示不同结构 */
/** 纯文本化：块体是纯文本，去掉 markdown 粗体/行内代码记号，免得看到 **55** */
function plainText(v: string): string {
  return (v || "").replace(/\*\*/g, "").replace(/`/g, "");
}

function stepView(s: Step): { text: string; code: boolean } {
  if (s.kind !== "tool") return { text: plainText(s.detail || ""), code: false };
  try {
    const j = JSON.parse(s.detail || "{}");
    const tool = String(j.tool || "");
    const a = j.args || {};
    if (tool === "delegate_task_to_member") {
      return { text: String(a.task || ""), code: false };
    }
    if (/sql/i.test(tool)) {
      return { text: String(a.query || a.sql || JSON.stringify(a, null, 2)), code: true };
    }
    if (/search|kb|retriev/i.test(tool)) {
      const q = a.query || a.q || a.keyword || "";
      return { text: `检索：${q}\n${JSON.stringify(a, null, 2)}`, code: true };
    }
    // 单参数工具（最常见）：内容型参数只显示值，其它显示 key=value
    // （只显示 "1000" 读者看不懂，显示 "limit=1000" 至少知道限了多少条）
    const keys = Object.keys(a);
    if (!keys.length) return { text: "（无参数）", code: false };
    if (keys.length === 1 && typeof a[keys[0]] !== "object") {
      const k = keys[0];
      const v = String(a[k]);
      const contentKeys = ["question", "query", "q", "keyword", "task", "text", "name", "url", "sql"];
      return { text: contentKeys.includes(k) ? v : `${k}=${v}`, code: false };
    }
    return { text: JSON.stringify(a, null, 2), code: true };
  } catch {
    return { text: s.detail || "", code: false };
  }
}

/** 把后端返回的步骤行折叠成块（工具结果内联、回话合并） */
function foldRows(rows: any[]): Step[] {
  const folded: Step[] = [];
  rows.forEach((r: any) => {
    const one: Step = {
      kind: r.kind,
      title: r.title,
      actor: r.agent_name || "",
      detail: (r.detail || "").trim(),
      time: r.time,
      open: false
    };
    // 工具步骤自带返回值（真实工具调用的结果）→ 直接作为结果块
    if (one.kind === "tool") {
      try {
        const j = JSON.parse(one.detail || "{}");
        if (j.result) one.result = String(j.result).slice(0, 600);
      } catch {
        /* detail 不是 JSON：忽略 */
      }
    }
    if (one.kind === "reply") {
      // 只回填到「派给他的那一块」：如果他在派活之后自己调过工具，
      // 那些工具块已经各自带结果了，回话就单独成块（更像真实 harness 的顺序）
      const who = (one.actor || one.title.replace(" 回话", "")).trim();
      let di = -1;
      for (let k = folded.length - 1; k >= 0; k--) {
        if (folded[k].kind === "tool" && toolTarget(folded[k]) === who) {
          di = k;
          break;
        }
      }
      if (di >= 0) {
        const usedTools = folded.slice(di + 1).some((x) => x.kind === "tool" && x.actor === who);
        if (!usedTools) {
          folded[di].result = one.detail;
          folded[di].replyTime = one.time;   // 回话时间要留着，面板上显示"派活 → 回话"
          return;
        }
      }
    }
    folded.push(one);
  });
  return folded;
}

async function loadSteps(agentId: number) {
  try {
    const res: any = await getOfficeSteps({ agent_id: agentId, limit: 40 });
    const rows = (res?.data?.data || []).slice().reverse();
    steps.value = foldRows(rows);
  } catch {
    steps.value = [];
  }
}

/** 「最近一轮执行」：没有本地帧可重放时，直接把最近一次落库的 run 摊开看 */
/** 打开某一次派活的执行过程；不给 run_id 就取最近一次 */
async function openRun(runId?: string) {
  try {
    const res: any = await getOfficeSteps(runId ? { run_id: runId, limit: 120 } : { limit: 80 });
    let rows: any[] = res?.data?.data || [];
    if (!rows.length) {
      ElMessage.info(runId ? "这一次没有步骤记录" : "还没有执行记录，先派个活试试");
      return;
    }
    if (!runId) {
      const newest = rows[0].run_id;
      rows = rows.filter((r) => r.run_id === newest);
    }
    rows = rows.slice().reverse();
    const who =
      rows.find((r) => r.kind === "plan")?.agent_name ||
      rows.find((r) => r.agent_name)?.agent_name ||
      "";
    const a =
      agents.value.find((x) => x.name === who) ||
      agents.value.find((x) => x.isLeader) ||
      agents.value[0];
    if (!a) return;
    activeRun.value = rows[0]?.run_id || runId || null;
    await openDetail(a.id);
    steps.value = foldRows(rows);
    // 看历史那一轮：从头读，不要自动滚到底（滚到底只用于"正在跑"）
    await nextTick();
    stickBottom.value = false;
    showJumpLatest.value = false;
    if (stepsBodyRef.value) stepsBodyRef.value.scrollTop = 0;
    /* 内容比面板高时，立刻给「回到最新」（历史轮次默认不在底部） */
    await nextTick();
    onStepsScroll();
    office?.setScreen?.(
      "log",
      {
        title: a.name,
        sub: `${steps.value.length} 步 · ${rows[0]?.time || ""}`,
        busy: false,
        entries: steps.value.slice(-4).map((st) => ({
          kind: st.kind,
          actor: st.actor || "组长",
          tool: st.kind === "tool" ? toolName(st) : "",
          to: st.kind === "tool" ? toolTarget(st) : "",
          text: stepView(st).text,
          result: st.result || ""
        }))
      },
      { focus: false }
    );
  } catch (e: any) {
    ElMessage.error(e?.message || "读取执行记录失败");
  }
}

/** 任务列表（按天筛选 + 分页） */
async function loadTasks(page = taskPage.value) {
  taskLoading.value = true;
  try {
    const res: any = await getOfficeRuns({
      page_no: page,
      page_size: taskPageSize,
      date: taskDate.value || undefined,
      days: 30,
      status: taskStatus.value || undefined,
      agent_name: taskAgent.value || undefined
    });
    const d = res?.data?.data || {};
    tasks.value = d.items || [];
    taskTotal.value = d.total || 0;
    taskPage.value = d.page_no || page;
  } catch {
    tasks.value = [];
    taskTotal.value = 0;
  } finally {
    taskLoading.value = false;
  }
}

/** 换筛选：回到第一页 */
function reloadTasks() {
  loadTasks(1);
}

/**
 * 定时任务在办公室可见：盯任务列表里「定时任务：」开头的 run。
 * 开工 → 组长播报 + 负责人回工位干活 + 白板写任务；收尾 → 再报一次结果。
 */
const cronBanner = ref<any>(null);
const seenCron = new Set<string>();
let cronPrimed = false;

function reactCron(run: any) {
  const name = String(run.prompt || "").replace(/^定时任务：/, "").trim() || "定时任务";
  const agent = run.leader || "";
  const status = run.status || "running";
  cronBanner.value = { name, agent, status, ms: run.duration_ms || 0, runId: run.run_id };
  office?.cronRun?.({ name, agent, status, ms: run.duration_ms || 0 });
  if (status === "running") {
    addCast("cron", `定时任务「${name}」开始执行${agent ? ` · ${agent}` : ""}`);
    if (camMode.value === "follow" && agent) followIfNeeded(agent);
  } else if (status === "error") {
    addCast("cron", `定时任务「${name}」失败${run.error ? `：${run.error}` : ""}`, true);
  } else {
    addCast(
      "cron",
      `定时任务「${name}」完成${run.duration_ms ? ` · ${Math.max(1, Math.round(run.duration_ms / 1000))} 秒` : ""}`
    );
  }
  if (status !== "running") {
    window.setTimeout(() => {
      if (cronBanner.value && cronBanner.value.runId === run.run_id) cronBanner.value = null;
    }, 9000);
  } else {
    /* 兜底：这一轮要是永远不收尾（服务重启 / 跨天从列表里消失），
       提示条不能一直挂"执行中"，10 分钟后自己收掉 */
    window.setTimeout(() => {
      const b = cronBanner.value;
      if (b && b.runId === run.run_id && b.status === "running") cronBanner.value = null;
    }, 10 * 60 * 1000);
  }
}

async function pollCron() {
  try {
    const res: any = await getOfficeRuns({ page_no: 1, page_size: 8, days: 1 });
    const items: any[] = res?.data?.data?.items || [];
    const cronItems = items.filter((x: any) => String(x.prompt || "").startsWith("定时任务："));
    if (!cronPrimed) {
      cronPrimed = true;
      cronItems.forEach((x: any) => seenCron.add(x.run_id));
      /* 刚进页面：只有「正在跑」的那条值得播一次，历史的不重播 */
      const running = cronItems.find((x: any) => x.status === "running");
      if (running) reactCron(running);
      return;
    }
    cronItems
      .slice()
      .reverse()
      .forEach((x: any) => {
        if (seenCron.has(x.run_id)) {
          /* 之前播过「进行中」，现在收尾了 → 补一条结果 */
          const b = cronBanner.value;
          if (b && b.runId === x.run_id && b.status === "running" && x.status !== "running") {
            reactCron(x);
          }
          return;
        }
        seenCron.add(x.run_id);
        /* 页面常开几天的话这个 Set 会一直长：保留最近 200 条就够判重了 */
        if (seenCron.size > 200) {
          const oldest = seenCron.values().next().value;
          if (oldest) seenCron.delete(oldest);
        }
        reactCron(x);
      });
  } catch {
    /* 轮询失败静默 */
  }
}

/** 底部流水条：今天最近 3 次派活（点一下看那一次） */
async function loadRecent() {
  try {
    const res: any = await getOfficeRuns({ page_no: 1, page_size: 3, days: 1 });
    recentTasks.value = (res?.data?.data?.items || []).slice(0, 3);
  } catch {
    recentTasks.value = [];
  }
}

function pushStep(kind: string, title: string, detail = "", actor = "") {
  if (kind === "reply" && actor) {
    const idx = steps.value.findIndex((x) => x.kind === "tool" && toolTarget(x) === actor);
    const usedTools =
      idx >= 0 && steps.value.slice(idx + 1).some((x) => x.kind === "tool" && x.actor === actor);
    if (idx >= 0 && !usedTools) {
      const copy = steps.value.slice();
      copy[idx] = { ...copy[idx], result: detail };
      steps.value = copy;
      return;
    }
  }
  steps.value = [
    ...steps.value,
    { kind, title, actor, detail, time: new Date().toTimeString().slice(0, 8), open: false }
  ];
}

/** 楼层：1F / 2F（二层是同一套布局叠上去，容量翻倍） */
const floor = ref<1 | 2>(1);
function switchFloor(n: 1 | 2) {
  floor.value = n;
  /* 平滑过渡：硬切会"跳"一下（人眼会以为页面闪了） */
  office?.focusFloor?.(n, true);
  /* 记住上次看的楼层：刷新 / 从别的页面回来不用再手动切 */
  try {
    localStorage.setItem("ai_office_floor", String(n));
  } catch {
    /* 隐私模式写不了 localStorage，忽略 */
  }
}

/** 视角：室内 / 露台（露台是加座区，人多时用得上） */


/* ---------- 形象编辑：颜色/发型当场生效，按 agent id 存本地 ---------- */
const HAIR_STYLES = [
  { key: "short", label: "短发" },
  { key: "side", label: "侧分" },
  { key: "bowl", label: "锅盖" },
  { key: "bun", label: "丸子头" },
  { key: "long", label: "长发" }
];
const SHIRT_COLORS = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981", "#0ea5e9", "#f97362", "#ec4899", "#64748b"];
const PANTS_COLORS = ["#334155", "#3f3f46", "#44403c", "#1f2937", "#4b5563", "#6b7280"];
const SHOE_COLORS = ["#39414d", "#2b303a", "#5b4636", "#e8ecf2", "#8b5a3c", "#3b4a5e"];
const HAIR_COLORS = ["#2f343d", "#3a3129", "#4a3a2c", "#584a3c", "#8a6a4a", "#2c323b"];

const LOOK_KEY = "office:looks";
const lookDraft = ref<Record<string, string>>({});

function loadLooks(): Record<string, Record<string, string>> {
  try {
    return JSON.parse(localStorage.getItem(LOOK_KEY) || "{}");
  } catch {
    return {};
  }
}

function applyLook(patch: Record<string, string>) {
  const d: any = detail.value;
  if (!d) return;
  lookDraft.value = { ...lookDraft.value, ...patch };
  office?.setLook?.(d.name, patch);
  const all = loadLooks();
  all[d.id] = { ...(all[d.id] || {}), ...patch };
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify(all));
  } catch {
    /* 存不下就算了 */
  }
}

/** 打开页面时把存过的形象刷回去 */
function restoreLooks() {
  const all = loadLooks();
  Object.entries(all).forEach(([id, patch]) => {
    const a = agents.value.find((x) => String(x.id) === String(id));
    if (a) office?.setLook?.(a.name, patch);
  });
}

/** 场景里的大屏（简报 / 结论都渲到 3D 屏幕上，不再浮层） */
const isNight = ref(false);
function showResultOnScreen() {
  office?.setScreen?.("result", {
    title: resultTitle.value,
    text: resultText.value,
    hint: resultSessionId.value ? "已存为会话，可在工作台的会话列表里追溯" : ""
  });
}
const resultTitle = ref("组长结论");
const resultText = ref("");
const resultSessionId = ref<number | null>(null);
/* 点名派活 */
const oneText = ref("");
const oneLoading = ref(false);
const oneAbort = ref<AbortController | null>(null);

/* 详情抽屉 */
const detail = ref<any>(null);
const models = ref<any[]>([]);

let office: any = null;
let pollTimer: any = null;
let cronTimer: any = null;

const onDuty = computed(() => agents.value.length);

/** 组长名（顶栏派活文案里点名，避免"组长"这种内部叫法） */
const leaderName = computed(
  () => (agents.value.find((a) => a.isLeader) || agents.value[0] || {}).name || "组长"
);
const overflow = computed(() => Math.max(0, agents.value.length - seated.value));
const filtered = computed(() =>
  agents.value.filter((a) => !keyword.value || a.name.includes(keyword.value))
);

async function load(silent = false) {
  if (!silent) loading.value = true;
  try {
    const res: any = await getAiAgentOffice();
    const list: any[] = res?.data?.data || res?.data || [];
    agents.value = list.map((a) => ({
      id: a.id,
      name: a.name || "未命名",
      role: a.role || "",
      status: (a.status === "error" ? "error" : a.status === "busy" ? "busy" : "idle") as OfficeAgent["status"],
      task: a.task || "",
      last_active: a.last_active || null,
      isLeader: !!a.is_leader
    }));
    office?.setAgents(agents.value);
    seated.value = office ? office.count() : 0;
  } catch (e: any) {
    if (!silent) ElMessage.error(e?.message || "加载智能体失败");
  } finally {
    if (!silent) loading.value = false;
    booting.value = false;
  }
}

function pick(id: number) {
  const next = selected.value === id ? null : id;
  selected.value = next;
  office?.select(next);
  if (next) {
    /* 先等工牌画完（showBadge 自己会把"人 + 大屏"框进画面），
       再把人推近：否则两处 focusCamera 打架，最后停在远景。 */
    void openDetail(next).then(() => {
      const who = agents.value.find((a) => a.id === next)?.name;
      if (who && selected.value === next && camMode.value !== "follow") {
        office?.focusAgent?.(who, 2.2);
      }
    });
  } else {
    clearPick();
  }
}

/* ---------- 详情抽屉 ---------- */
const statusText = computed(() => {
  const st = agents.value.find((a) => a.id === detail.value?.id)?.status;
  return st === "busy" ? "工作中" : st === "wait" ? "等你确认" : "在岗";
});
const statusTag = computed<"primary" | "warning" | "info">(() =>
  statusText.value === "工作中" ? "primary" : statusText.value === "等你确认" ? "warning" : "info"
);
/* 分类功能已在 main 下线（后端 category 路由删除）：这里改用角色，别再依赖分类树 */
const categoryName = computed(() => detail.value?.agent_role || "未分类");
const modelName = computed(() => {
  const mid = detail.value?.model_id;
  if (!mid) return "默认模型";
  return models.value.find((m) => m.id === mid)?.name || `#${mid}`;
});
const lastActive = computed(() => {
  const a = agents.value.find((x) => x.id === detail.value?.id);
  return a?.last_active || "暂无记录";
});
const caps = computed(() => {
  const d = detail.value || {};
  const out: { text: string; type: any }[] = [];
  if (d.tool_ids?.length) out.push({ text: `工具 ${d.tool_ids.length}`, type: "warning" });
  if (d.skill_ids?.length) out.push({ text: `技能 ${d.skill_ids.length}`, type: "success" });
  if (d.knowledge_ids?.length) out.push({ text: `知识库 ${d.knowledge_ids.length}`, type: "success" });
  if (d.mcp_ids?.length) out.push({ text: `MCP ${d.mcp_ids.length}`, type: "danger" });
  if (d.workflow_id) out.push({ text: "工作流编排", type: "primary" });
  return out;
});

async function openDetail(id: number) {
  detail.value = null;
  try {
    const res: any = await getAiAgentDetail(id);
    const d = res?.data?.data || res?.data || null;
    // 后端返回 agent_name，页面统一用 name
    detail.value = d ? { ...d, name: d.agent_name || d.name || "未命名" } : null;
    await showBadge();
  } catch (e: any) {
    ElMessage.error(e?.message || "加载详情失败");
  }
}

/** 取消选中：收工牌、回到"交给组长"模式 */
function clearPick() {
  selected.value = null;
  lookOpen.value = false;
  office?.select?.(null);
  office?.hideBadge?.();
  office?.setScreen?.("idle", null, { focus: false });
  /* 默认视角下取消选中 = 镜头也退回全景（选了白板/大屏预设时不动，免得抢用户的视角） */
  if (camMode.value === "overview") office?.cameraPreset?.("overview");
  steps.value = [];
  detail.value = null;
}

/** 把人信息画进场景里的工牌（不再开抽屉） */
async function showBadge() {
  const d: any = detail.value;
  if (!d) return;
  const st = agents.value.find((a) => a.id === d.id)?.status || "idle";
  lookDraft.value = loadLooks()[d.id] || {};
  await loadSteps(d.id);
  /* 工作日志：优先显示"正在做什么"（实时），再补一条最近调用 */
  const live = agents.value.find((a) => a.id === d.id);
  const logs: string[] = [];
  if (live?.task) logs.push(`正在做：${live.task.replace(/^组长派单：|^派单：/, "")}`);
  runs.value
    .filter((r) => r.app_id === d.id)
    .slice(0, logs.length ? 1 : 2)
    .forEach((r) => {
      logs.push(`${r.time} ${usageLabel(r.usage)} ${r.result === "success" ? "成功" : "失败"}`);
    });
  const myRuns = logs;

  /* 工具级时间线：有工具记录就用工具（tool / 耗时 / 成败），没有就退回调用记录 */
  let toolEntries: { t: string; k: string; ms: number | null; ok: boolean }[] = [];
  try {
    const tr: any = await getAiToolCalls(d.id, 6);
    const list = tr?.data?.data || [];
    toolEntries = list.map((x: any) => ({
      t: String(x.time || "").slice(0, 8),
      k: String(x.tool || "").slice(0, 12),
      ms: x.duration_ms ?? null,
      ok: !!x.ok
    }));
  } catch {
    toolEntries = [];
  }
  /* 墙上大屏切成这个人的工作日志（只换内容，镜头继续对着人） */
  office?.setScreen?.(
    "log",
    {
      title: d.name,
      sub: `${statusText.value} · ${categoryName.value}`,
      busy: live?.status === "busy",
      entries: steps.value.slice(-4).map((st) => ({
        kind: st.kind,
        actor: st.actor || "组长",
        tool: st.kind === "tool" ? toolName(st) : "",
        to: st.kind === "tool" ? toolTarget(st) : "",
        text: stepView(st).text,
        result: st.result || ""
      }))
    },
    { focus: false }
  );
  office?.showBadge?.({
    id: d.id,
    logs: myRuns,
    name: d.name,
    role: d.agent_role || "",
    status: st,
    model: modelName.value,
    last: lastActive.value,
    caps: caps.value.map((c: any) => c.text)
  });
}

async function loadMeta() {
  try {
    const m: any = await getAiModelList({});
    models.value = m?.data?.data || m?.data || [];
  } catch {
    models.value = [];
  }
}

function openWorkspace() {
  router.push("/ai/workspace");
}

function goLogs() {
  router.push("/ai/logs");
}

/** 派活给组长：后端用 agno Team(coordinate) 协同，结论统一从组长出 */
/** 连接断开提示（不自动消失，用户点掉或重试才走） */
const connLost = ref<{ reason: string; retry?: () => void } | null>(null);

function fmtMs(ms?: number): string {
  const v = Number(ms || 0);
  if (!v) return "—";
  return v < 1000 ? `${v}ms` : `${(v / 1000).toFixed(1)}s`;
}

/** 顶部统计条：静默刷新（复用简报的 summary，不弹窗、不上大屏） */
async function loadSummary() {
  try {
    const res: any = await getOfficeSummary();
    if (res?.data?.data) summary.value = res.data.data;
  } catch {
    /* 统计失败就保持旧值，不影响主流程 */
  }
}

function retryAfterLost() {
  const fn = connLost.value?.retry;
  connLost.value = null;
  fn?.();
}

/** 把各种异常翻译成人话（fetch 的 TypeError 只有 "Failed to fetch"） */
function describeErr(e: any): string {
  const msg = String(e?.message || e || "").trim();
  if (/Failed to fetch|NetworkError|network error|ERR_|ECONN/i.test(msg)) return "网络中断";
  if (/提前中断/.test(msg)) return "数据流被提前关闭（代理/网关超时？）";
  if (/^派活失败（\d+）$/.test(msg)) return msg;
  return msg.slice(0, 120) || "未知错误";
}

/**
 * 断线后确认服务端到底跑完没有。
 *
 * 流断了不代表这一轮一定失败：有时是网关把响应掐了，服务端其实已经跑完并落库。
 * 这里按"任务文本前 30 字"找最近的一轮，把结论补回页面（找不到就保持"已中断"）。
 */
async function recoverAfterDrop(prompt: string, who?: string) {
  const key = prompt.replace(/\s+/g, "").slice(0, 30);
  for (let i = 0; i < 4; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const res: any = await getOfficeRuns({ page_no: 1, page_size: 5 });
      const items: any[] = res?.data?.data?.items || [];
      const hit = items.find((x: any) => {
        const p = String(x.prompt || "").replace(/\s+/g, "");
        if (!key || !p.startsWith(key)) return false;
        if (who && x.leader !== who) return false;
        return x.status === "ok" || x.status === "error";
      });
      if (!hit) continue;
      const st: any = await getOfficeSteps({ run_id: hit.run_id, limit: 80 });
      const rows = (st?.data?.data || []).slice().sort((a: any, b: any) => a.seq - b.seq);
      const last = [...rows].reverse().find((x: any) => x.kind === "summary" || x.kind === "error");
      if (!last) continue;
      resultTitle.value = `组长 ${hit.leader || ""} 的结论`;
      resultText.value = last.detail || "";
      briefText.value = (last.detail || "").slice(0, 80);
      activeRun.value = hit.run_id;
      pushStep(
        hit.status === "ok" ? "summary" : "error",
        hit.status === "ok" ? "断线后补回结论" : "断线后确认失败",
        (last.detail || "").slice(0, 300),
        hit.leader || ""
      );
      connLost.value = null;
      if (hit.status === "ok") {
        ElMessage.success("连接断了，但这一轮其实跑完了，结论已补回来");
      } else {
        ElMessage.warning("连接断了，服务端记录这一轮是失败的（详见执行过程）");
      }
      loadRuns();
      loadTasks(1);
      loadRecent();
      return;
    } catch {
      /* 单次失败继续等 */
    }
  }
}

async function doDispatch() {
  const text = dispatchText.value.trim();
  if (!text) {
    ElMessage.warning("先说一句要做什么");
    return;
  }
  /* 双保险：按钮已经禁用，但回车/快捷键也可能触发第二次 */
  if (dispatching.value) return;
  dispatching.value = true;
  connLost.value = null;
  office?.clearBubbles?.();
  steps.value = [];
  stickBottom.value = true;
  showJumpLatest.value = false;
  rememberPrompt(text);
  addCast("info", `派活：${text.slice(0, 60)}`);
  /* 立刻让组长进入「工作中」：服务端装配 Team（成员建 agent + 知识库检索）要 20 秒上下，
     这期间名单/名牌还是「待命」，用户点了以为没反应。后端也会在收到任务时立刻打点，
     这里先本地亮起来，轮询回来再以后端为准。 */
  {
    const leader = agents.value.find((a: any) => a.isLeader) || agents.value[0];
    if (leader) {
      office?.engage?.(leader.name);
      office?.writeBoard?.([`收到任务：${text.slice(0, 26)}`, "组长正在拆解任务…"]);
      leader.status = "busy";
      leader.task = "正在拆解任务…";
    }
  }
  const ctrl = new AbortController();
  dispatchAbort.value = ctrl;
  const watchdog = window.setTimeout(() => ctrl.abort("timeout"), DISPATCH_TIMEOUT_MS);
  let midTimer: number | null = null;
  try {
    let doneFrame: any = null;
    const roster: string[] = [];
    /* 跑超过 90 秒还没结束：把大家叫回白板同步一次进度（只同步一次） */
    let synced = false;
    midTimer = window.setInterval(() => {
      if (synced || !dispatching.value) return;
      synced = true;
      office?.midSync?.(roster, "任务有点长，先同步一下进度");
      pushStep("tool", "中途同步", "任务超过 90 秒，组长把大家叫回白板对了一次进度", "");
    }, 90000);
    const division: { who: string; task: string; done?: boolean }[] = [];
    const t0 = performance.now();
    const frames: RunFrame[] = [];
    await streamOfficeDispatch(text, (f: any) => {
      if (f.type === "delegate" || f.type === "reply") {
        // 运行中就把「谁派给谁 / 谁回了什么」冒出来
        office?.say?.({ ...f, kind: f.type });
        frames.push({
          t: Math.round(performance.now() - t0),
          type: f.type,
          from: f.from,
          to: f.to,
          text: f.text,
          task: f.task
        });
        if (f.type === "delegate") {
          if (f.to && !roster.includes(f.to)) roster.push(f.to);
          refreshSoon(f.to);
          office?.ping?.(f.to);
          office?.engage?.(f.to);
          office?.lookAtLeader?.(f.to, 4);
          addCast("delegate", castHandoff(f.from, f.to, f.task));
          followIfNeeded(f.to);
          /* 协同可视化：组长 → 组员拉一条任务线，名牌上标"受命/等待" */
          office?.handoff?.(f.from, f.to);
          /* 组长本人走过去交代一句（只走第一次，后面并派不再折返） */
          if (!roster.length) office?.leaderVisit?.(f.to);
          /* 白板上的分工跟着更新：谁负责哪一段 */
          division.push({ who: f.to, task: f.task || text });
          office?.taskBoard?.(text, division);
          pushStep("tool", `派活 → ${f.to}`, JSON.stringify({ tool: "delegate_task_to_member", args: { member: f.to, task: f.task || "" } }), f.from || "");
        } else {
          office?.replyDone?.(f.from);
          /* 白板分工打勾：这个人交结果了 */
          const row = division.find((r) => r.who === f.from);
          if (row) {
            row.done = true;
            office?.taskBoard?.(text, division);
          }
          pushStep("reply", `${f.from} 回话`, f.text || "", f.from || "");
          addCast("reply", `${f.from || "成员"} 回话：${f.text || ""}`);
          followIfNeeded(f.from);
        }
      } else if (f.type === "tool") {
        // 组长/组员真实调用工具：立刻落一行（工具名 + 参数 + 返回）
        pushStep(
          "tool",
          String(f.tool || "tool"),
          JSON.stringify({ tool: f.tool, args: f.args || {}, result: f.result || "" }),
          f.from || ""
        );
        if (f.from) {
          refreshSoon(f.from);
          office?.ping?.(f.from);
          office?.toolScreen?.(f.from, f.tool);
          addCast("tool", `${f.from} 调用 ${f.tool || "工具"}`);
          followIfNeeded(f.from);
        }
      } else if (f.type === "queue") {
        /* 目标在忙：后端排队执行（方案 A），先给个交代，别让人以为卡住了 */
        const ahead = Number(f.ahead || 0);
        addCast("conn", `前面还有 ${ahead} 个任务在跑，已排队，轮到会自动开始`);
        office?.writeBoard?.([
          `任务：${text.slice(0, 26)}`,
          `排队中：前面还有 ${ahead} 个任务`
        ]);
      } else if (f.type === "start") {
        hasMemory.value = !!f.memory;
        // 有成员的模型配置坏了（被跳过）：说清楚，别让人以为"他没干活"
        const skipped = (f.skipped || []).filter(Boolean);
        if (skipped.length) {
          const msg = `${skipped.join("、")} 的模型配置不可用，本轮跳过（请到「模型配置」检查绑定）`;
          ElMessage.warning(msg);
          addCast("conn", msg, true);
        }
        // 有活干了：正在摸鱼的人陆续回工位
        office?.backToDesks?.();
        /* 开工动员：全员先到白板前站一下，白板写"当前任务 + 分工" */
        const team = (f.members || []).filter((n: string) => n !== f.leader);
        if (team.length) office?.kickoff?.(team, 4500);
        office?.taskBoard?.(text, []);
        if (skipped.length) {
          office?.writeBoard?.([
            `任务：${text.slice(0, 26)}`,
            `⚠ ${skipped.join("、")} 模型配置不可用，本轮跳过`,
            "点右侧「执行过程」看详情"
          ]);
        }
        pushStep("plan", `收到任务：${text.slice(0, 40)}`, text, f.leader || "");
      } else if (f.type === "done") {
        doneFrame = f;
      }
    }, ctrl.signal);
    if (!doneFrame) {
      /* 流正常结束却没收到结束帧 = 被中途掐断（代理缓冲/网关超时），不能当成功 */
      throw new Error("连接提前中断（没收到结束帧）");
    }
    const d = doneFrame;
    if (d.ok === false) {
      const why = String(d.error || "组长处理失败");
      ElMessage.error(why);
      addCast("conn", `派活失败：${why}`, true);
      office?.failBeam?.(roster[roster.length - 1] || "", 5);
      /* 白板也写清楚失败原因，别让看大屏的人只知道"失败了" */
      office?.writeBoard?.([
        `任务失败：${text.slice(0, 26)}`,
        why.slice(0, 60),
        "点右侧「执行过程」看详情"
      ]);
      return;
    }
    // 收尾表演：组长走到白板前公布结论，参会的抬头听，然后各自回座
    // 取「像结论的一行」：跳过 "…如下：" 这种引言行
    const lines = (d.content || "")
      .split("\n")
      .map((l: string) => l.replace(/^[#>*\-\s]+/, "").replace(/\*\*/g, "").trim())
      .filter((l: string) => l.length > 0);
    const summary =
      lines.find((l: string) => l.length >= 6 && !/[：:]$/.test(l)) || lines[0] || "";
    // 组长走到白板前把结论说出来（纯表演，结论条已经先亮）
    wrapHint.value = "组长去白板公布结论…";
    office?.wrapUp?.({ leader: d.leader, members: roster, text: summary.slice(0, 46) });
    if (roster.length >= 2) {
      /* 多人协作：参会的都走到白板前听组长讲结论（9 秒后自己回座），
         这里不能再调 release —— 它会把刚走到白板的人又赶去休息区 */
      office?.gatherAtBoard?.(roster, 9000);
    } else {
      office?.release?.(roster);
    }
    window.setTimeout(() => { wrapHint.value = ""; }, 2600);
    resultTitle.value = `组长 ${d.leader || ""} 的结论`;
    resultText.value = d.content || "（组长没有返回内容）";
    resultSessionId.value = d.session_id || null;
    pushStep("summary", "组长汇总", resultText.value.slice(0, 300), d.leader || "");
    addCast("summary", `结论：${summary || resultText.value.slice(0, 60)}`);
    briefText.value = summary || resultText.value.slice(0, 80);
    pushBoard(summary || resultText.value);
    saveRun({ at: new Date().toISOString(), leader: d.leader, members: roster, summary, frames });
    dispatchText.value = "";
    activeRun.value = d.run_id || null;
    load(true);
    loadRuns();
    loadTasks(1);
    loadRecent();
    window.setTimeout(refreshPartyState, 800);
  } catch (e: any) {
    if (ctrl.signal.aborted) {
      ElMessage.info(
        ctrl.signal.reason === "timeout" ? "超过 5 分钟，已自动停止" : "已停止这一轮"
      );
      pushStep("error", "已停止", "下面是停止之前跑完的步骤");
      addCast("info", ctrl.signal.reason === "timeout" ? "超时自动停止" : "手动停止了这一轮");
    } else {
      const reason = describeErr(e);
      pushStep("error", "连接断开", reason);
      addCast("conn", `连接断开：${reason}`, true);
      office?.writeBoard?.([
        "连接断开",
        reason.slice(0, 60),
        "可点上方「重试这一轮」"
      ]);
      connLost.value = {
        reason,
        retry: () => {
          dispatchText.value = text;
          doDispatch();
        }
      };
      void recoverAfterDrop(text);
    }
  } finally {
    window.clearTimeout(watchdog);
    if (midTimer) window.clearInterval(midTimer);
    dispatchAbort.value = null;
    dispatching.value = false;
  }
}

/** 失败重试：把那条任务原样再派一次 */
async function retryRun(t: any) {
  if (!t?.prompt) return;
  try {
    await ElMessageBox.confirm(
      `将按原来的任务重新派活一次：\n「${String(t.prompt).slice(0, 60)}」`,
      "重试这一轮",
      { confirmButtonText: "重试", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  dispatchText.value = t.prompt;
  await nextTick();
  doDispatch();
}

/** 顶栏「停止」：中断这一轮（后端连接一断，生成器随之取消） */
function stopDispatch() {
  dispatchAbort.value?.abort("user");
}

/* ---------- 迟到：9:30 之后进页面，有人从门口走进来 ---------- */
/* ---------- 今日简报 ---------- */
const summary = ref<any>({
  date: "",
  total: 0,
  team: 0,
  agent: 0,
  people: 0,
  avg_ms: 0,
  errors: 0,
  error_rate: 0,
  runs: { total: 0, errors: 0, error_rate: 0, avg_ms: 0, last_time: null },
  last_time: null,
  top: [] as { id: number; name: string; count: number }[]
});

async function openSummary() {
  try {
    const res: any = await getOfficeSummary();
    summary.value = res?.data?.data || summary.value;
    office?.setScreen?.("brief", summary.value);
  } catch (e: any) {
    ElMessage.error(e?.message || "取简报失败");
  }
}

function pct(n: number) {
  const max = Math.max(1, ...(summary.value.top || []).map((t: any) => t.count));
  return Math.round((n / max) * 100);
}

/* ---------- 回放：把上一轮协同原样重演 ---------- */
const RUN_KEY = "office:lastRun";

function saveRun(run: RunRec) {
  lastRun.value = run;
  try {
    sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
  } catch {
    /* 存不下就算了，内存里还能重播 */
  }
}

function loadRun() {
  try {
    const raw = sessionStorage.getItem(RUN_KEY);
    if (!raw) return;
    const run = JSON.parse(raw) as RunRec;
    if (run && Array.isArray(run.frames) && run.frames.length) lastRun.value = run;
  } catch {
    /* 坏数据忽略 */
  }
}

/** 重演：帧按原始节奏（压缩到 55%）依次冒气泡，最后组长去白板收尾 */
function replayLast() {
  const run = lastRun.value;
  if (!run || !run.frames.length || replaying.value) return;
  replaying.value = true;
  wrapHint.value = "回放上一轮协同…";
  office?.clearBubbles?.();
  office?.backToDesks?.();

  let acc = 300;
  let prev = run.frames[0].t;   // 第一帧立刻出，不要干等它原本的耗时
  run.frames.forEach((fr) => {
    const gap = Math.max(260, (fr.t - prev) * 0.55);
    prev = fr.t;
    acc += gap;
    const payload = { ...fr, kind: fr.type };
    window.setTimeout(() => office?.say?.(payload), acc);
  });

  window.setTimeout(() => {
    office?.wrapUp?.({
      leader: run.leader,
      members: run.members,
      text: (run.summary || "").slice(0, 46)
    });
    window.setTimeout(() => {
      wrapHint.value = "";
      replaying.value = false;
    }, 2400);
  }, acc + 500);
}

/** 组员刚被点名：先把他的工位点亮（不用等 20 秒轮询） */
function refreshSoon(_name?: string) {
  window.setTimeout(() => load(true), 1200);
}

/** app_id → 智能体名字（日志里只有 id） */
function agentName(appId?: number | null): string {
  if (!appId) return "";
  return agents.value.find((a) => a.id === appId)?.name || "";
}

const USAGE_LABEL: Record<string, string> = {
  agent: "智能体",
  team: "组长协同",
  app: "应用",
  chat: "对话",
  workflow: "工作流",
  query: "问数",
  embedding: "向量化"
};
function usageLabel(u?: string): string {
  return USAGE_LABEL[u || ""] || u || "";
}

async function loadRuns() {
  try {
    const res: any = await getAiLogRecent(6);
    runs.value = res?.data?.data || res?.data || [];
  } catch {
    runs.value = [];
  }
}

/** 待确认数量：来自审批中心（动作写回 + 本体版本发布），不是编的 */
async function loadPending() {
  try {
    const res: any = await getApprovalCenter();
    const d = res?.data?.data || res?.data || {};
    pendingReview.value = Number(d.total || 0);
  } catch {
    pendingReview.value = 0;
  }
  office?.setBadge(pendingReview.value > 0 ? `待你确认 ${pendingReview.value}` : "");
}

async function dispatchOne() {
  const id = detail.value?.id;
  const text = oneText.value.trim();
  if (!id) return;
  if (!text) {
    ElMessage.warning("先写一句要他做什么");
    return;
  }
  oneLoading.value = true;
  connLost.value = null;
  const who = detail.value?.name || "";
  if (who) office?.engage?.(who);
  rememberPrompt(text);
  addCast("delegate", `派给 ${who || "成员"}：${text.slice(0, 50)}`);
  followIfNeeded(who);
  /* 单干也走协同那套：组长 → 这个人 拉任务线、名牌标受命、白板写任务 */
  const leaderName = agents.value.find((a: any) => a.isLeader)?.name;
  if (leaderName && who) office?.handoff?.(leaderName, who);
  office?.taskBoard?.(text, [{ who, task: text }]);
  const ctrl = new AbortController();
  oneAbort.value = ctrl;
  const watchdog = window.setTimeout(() => ctrl.abort("timeout"), DISPATCH_TIMEOUT_MS);
  try {
    const res: any = await dispatchOfficeAgent(id, text, ctrl.signal);
    const d = res?.data?.data || {};
    if (d.ok === false) {
      ElMessage.error(d.error || d.msg || "执行失败");
      addCast("conn", `${who || "成员"} 执行失败：${d.error || d.msg || ""}`, true);
      office?.failBeam?.(who, 5);
      return;
    }
    resultTitle.value = `${d.agent || detail.value?.name} 的结果`;
    resultText.value = d.content || "（没有返回内容）";
    resultSessionId.value = d.session_id || null;
    pushBoard(d.content || "");
    showResultOnScreen();
    /* 单干也把结论放进底部结论条：和团队派活保持一致，不用点开大屏才看得到 */
    const oneLine =
      String(d.content || "")
        .split("\n")
        .map((l: string) => l.replace(/^[#>*\-\s]+/, "").replace(/\*\*/g, "").trim())
        .find((l: string) => l.length >= 6 && !/[：:]$/.test(l)) || "";
    if (oneLine) briefText.value = oneLine.slice(0, 80);
    addCast("summary", `${who || "成员"} 完成：${oneLine || resultText.value.slice(0, 50)}`);
    oneText.value = "";
    await loadSteps(id);
    load(true);
    loadRuns();
  } catch (e: any) {
    if (ctrl.signal.aborted) {
      ElMessage.info(
        ctrl.signal.reason === "timeout" ? "超过 5 分钟，已自动停止" : "已停止这一次"
      );
    } else {
      const reason = describeErr(e);
      pushStep("error", "连接断开", reason);
      addCast("conn", `连接断开：${reason}`, true);
      connLost.value = {
        reason,
        retry: () => {
          oneText.value = text;
          dispatchOne();
        }
      };
      void recoverAfterDrop(text, who || undefined);
    }
  } finally {
    window.clearTimeout(watchdog);
    oneAbort.value = null;
    oneLoading.value = false;
    if (who) office?.release?.([who]);
  }
}

/** 单人派活的「停止」 */
function stopOne() {
  oneAbort.value?.abort("user");
}

function goApproval() {
  router.push("/ai/approval");
}

/** WebGL 上下文被系统回收（休眠/切显卡/驱动重置）：等它自己回来，回不来就给按钮重建 */
const glLost = ref(false);
const glReloading = ref(false);
/** 3 秒还没自动恢复：文案改成"建议直接重建"（有的驱动不给 restored 事件） */
const glStuck = ref(false);
let glLostTimer: number | null = null;

function handleGlLost() {
  glLost.value = true;
  glStuck.value = false;
  if (glLostTimer) window.clearTimeout(glLostTimer);
  glLostTimer = window.setTimeout(() => {
    if (glLost.value) glStuck.value = true;
    glLostTimer = null;
  }, 3000);
}

function handleGlRestored() {
  glLost.value = false;
  glStuck.value = false;
  if (glLostTimer) {
    window.clearTimeout(glLostTimer);
    glLostTimer = null;
  }
  ElMessage.success("3D 场景已恢复");
}

/** 建 3D 场景 + 让人物落座（首次进入与「重建场景」共用） */
async function mountOffice() {
  await nextTick();
  try {
    office = createOffice({
      stage: stageRef.value,
      plates: platesRef.value,
      onSelect: (id: number | null) => {
        selected.value = id;
        if (id) openDetail(id);
        else clearPick();
      },
      onBadgeClick: () => goApproval(),
      onNight: (v: boolean) => { isNight.value = v; },
      onFloorSwitch: (n: 1 | 2) => switchFloor(n),
      onContextLost: () => handleGlLost(),
      onContextRestored: () => handleGlRestored()
    });
    /* 恢复上次的楼层（默认 1F） */
    try {
      if (Number(localStorage.getItem("ai_office_floor") || 1) === 2) switchFloor(2);
    } catch {
      /* 读不到就当 1F */
    }
  } catch (e: any) {
    /* WebGL 上下文丢 / 初始化失败：别留一片空白，明确告诉用户发生了什么 */
    webglError.value = String(e?.message || e || "").slice(0, 120);
    booting.value = false;
    console.error("[office] 3D 初始化失败", e);
    return;
  }
  // 先等角色模型（拿不到就 false，自动用程序化小人）
  peopleHintTimer = window.setTimeout(() => {
    if (!peopleReady.value) peopleHint.value = true;
  }, 700);
  await office.ready?.();
  office.setAgents(agents.value);
  peopleReady.value = true;
  peopleHint.value = false;
  if (peopleHintTimer) {
    window.clearTimeout(peopleHintTimer);
    peopleHintTimer = null;
  }
  restoreLooks();
  applyQuality();          // 恢复上次的省电模式选择（重建场景后也要重新应用）
  seated.value = office.count();
  loadRun();
  loadBoard();
  // 开发期暴露句柄：无头浏览器验收靠它读位置/触发表演，生产构建会被摇掉
  if (import.meta.env.DEV) (window as any).__office = office;
}

/** 上下文回不来 / 用户主动：拆掉重建成新场景（不刷新页面，列表和执行过程都还在） */
async function rebuildOffice() {
  if (glReloading.value) return;
  glReloading.value = true;
  try {
    try {
      office?.dispose();
    } catch {
      /* 老场景已经坏了，dispose 抛错也继续 */
    }
    office = null;
    peopleReady.value = false;
    glLost.value = false;
    glStuck.value = false;
    await mountOffice();
    if (!webglError.value) ElMessage.success("3D 场景已重新加载");
  } finally {
    glReloading.value = false;
  }
}

/* ================= 快捷键（F） ================= */
/** 输入框/下拉里按键不算快捷键：别把人打字打断 */
function inEditable(el: EventTarget | null): boolean {
  const t = el as HTMLElement | null;
  if (!t) return false;
  const tag = (t.tagName || "").toLowerCase();
  return (
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    t.isContentEditable === true
  );
}
function onHotkey(e: KeyboardEvent) {
  /* Esc：按「弹层 → 下拉 → 选中 → 视角」的顺序一层层退，一次只退一层 */
  if (e.key === "Escape") {
    if (guideOpen.value) {
      closeGuide();
      return;
    }
    if (lookOpen.value) {
      lookOpen.value = false;
      return;
    }
    if (menuOpen.value) {
      menuOpen.value = false;
      return;
    }
    if (recentOpen.value) {
      recentOpen.value = false;
      return;
    }
    if (castOpen.value) {
      castOpen.value = false;
      return;
    }
    if (selected.value != null) {
      clearPick();
      return;
    }
    if (camMode.value !== "overview") setCamMode("overview");
    return;
  }
  if (inEditable(e.target)) return;
  /* 1 / 2 切楼层 */
  if (e.key === "1" || e.key === "2") {
    const n = e.key === "2" ? 2 : 1;
    if (floor.value !== n) switchFloor(n);
    return;
  }
  /* f：跟随开关（省得每次都去点按钮） */
  if (e.key === "f" || e.key === "F") {
    setCamMode(camMode.value === "follow" ? "overview" : "follow");
  }
}

onMounted(async () => {
  await load();
  loadMeta();
  await mountOffice();
  seated.value = office ? office.count() : 0;
  loadSummary();
  loadRuns();
  loadPending();
  loadTasks();
  loadRecent();
  pollCron();
  refreshPartyState();

  /* 本地记住的东西：播报展开状态、最近任务、引导是否看过 */
  try {
    castOpen.value = localStorage.getItem(CAST_KEY) === "1";
    const raw = localStorage.getItem(RECENT_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) recentPrompts.value = arr.slice(0, 5).map(String);
    }
    if (localStorage.getItem(GUIDE_KEY) !== "1") guideOpen.value = true;
    lowPower.value = localStorage.getItem(LOWPOWER_KEY) === "1";
  } catch {
    /* 隐私模式：都按默认值走 */
  }
  /* mountOffice 时还没读到本地设置，这里补一次（省电模式要在首屏就生效） */
  applyQuality();
  window.addEventListener("keydown", onHotkey);

  // 定时任务单独 8 秒轮询：到点要尽快看见，不能等 20 秒
  cronTimer = setInterval(() => {
    if (document.hidden) return;
    pollCron();
  }, 8000);

  // 20 秒轮询状态（页面隐藏时暂停）：静默刷新，不闪 loading，座位粘性保证人不挪窝
  pollTimer = setInterval(() => {
    if (document.hidden) return;
    load(true);
    loadRuns();
    loadPending();
    loadRecent();
    loadSummary();
    pollCron();
    refreshPartyState();
  }, 20000);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onHotkey);
  if (glLostTimer) window.clearTimeout(glLostTimer);
  glLostTimer = null;
  if (peopleHintTimer) window.clearTimeout(peopleHintTimer);
  peopleHintTimer = null;
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  if (cronTimer) clearInterval(cronTimer);
  cronTimer = null;
  office?.dispose();
  office = null;
});
</script>

<style lang="scss">
.ai-office-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  overflow: hidden;
  box-sizing: border-box;
  /* 有内容的底一律白色；蓝灰只做边框与间隔 */
  background: var(--el-bg-color);

  /* 舞台卡片顶端的一条工具条：不设大字标题，只放操作 */
  .office-bar {
    flex: 0 0 auto;
    padding: 8px 12px;
    border-bottom: 1px solid var(--el-border-color-light);
    background: var(--el-bg-color);
  }
  .office-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: nowrap;
  }
  .office-actions .tb-gap {
    flex: 1 1 auto;
  }
  .office-actions .dispatch-input {
    width: 280px;
  }
  /* 工具栏里的组分隔线：派活 / 楼层 / 更多 三段，别糊成一片按钮 */
  .office-actions .tb-sep {
    width: 1px;
    height: 16px;
    margin: 0 2px;
    background: var(--el-border-color-lighter);
  }

  .m-row .lead-tag {
    display: inline-block;
    margin-left: 4px;
    padding: 0 5px;
    border-radius: 3px;
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    font-size: 10.5px;
    font-weight: 500;
    line-height: 16px;
    vertical-align: 1px;
  }
  .result-hint {
    margin-top: 10px;
    font-size: 12px;
    color: var(--el-text-color-placeholder);
  }
  .result-body {
    white-space: pre-wrap;
    line-height: 1.75;
    font-size: 13px;
    color: var(--el-text-color-regular);
    max-height: 52vh;
    overflow-y: auto;
  }

  .office-body {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    gap: 12px;
  }

  /* 左栏固定 240 */
  .office-roster {
    flex: 0 0 240px;
    width: 240px;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--el-border-color-light);
    border-radius: 4px;
  }
  .office-roster :deep(.el-card__body) {
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
    padding: 14px;
  }
  .roster-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
  }
  .roster-head .t {
    font-size: 13px;
    font-weight: 600;
  }
  .roster-stat {
    margin-top: -4px;
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--el-text-color-secondary);
  }
  .roster-stat .num {
    color: var(--el-text-color-regular);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .roster-stat .warn {
    color: var(--el-color-warning);
  }
  .roster-stat .pending {
    cursor: pointer;
  }
  .roster-stat .pending:hover {
    text-decoration: underline;
  }
  .roster-list {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    margin: 0 -4px;
  }
  .m-row {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 6px 8px;
    border-radius: 4px;
    cursor: pointer;
  }
  /* 首字母头像：比一个光点更容易认人，状态用头像底色表达 */
  .m-row .m-av {
    flex: 0 0 24px;
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: var(--el-fill-color);
    color: var(--el-text-color-regular);
    font-size: 11px;
    font-weight: 600;
    transition: background-color 0.18s ease, color 0.18s ease;
  }
  .m-row .m-av.busy {
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    box-shadow: inset 0 0 0 1px var(--el-color-primary-light-7);
  }
  .m-row .m-av.wait {
    background: var(--el-color-warning-light-9);
    color: var(--el-color-warning);
  }
  .m-row .st {
    flex: 0 0 auto;
    align-self: flex-start;
    margin: 3px 0 0 auto;
    font-size: 11px;
    color: var(--el-text-color-placeholder);
  }
  .m-row .st.busy {
    color: var(--el-color-primary);
  }
  .m-row .st.error {
    color: var(--el-color-danger);
  }
  .m-row .m-av.error {
    background: var(--el-color-danger-light-9);
    color: var(--el-color-danger);
    box-shadow: inset 0 0 0 1px var(--el-color-danger-light-7);
  }
  .m-row .st.wait {
    color: var(--el-color-warning);
  }
  .m-row:hover {
    background: var(--el-fill-color-lighter);
  }
  .m-row.on {
    background: var(--el-color-primary-light-9);
  }
  .m-row .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: 0 0 7px;
    border: 1.4px solid #cdd3dc;
    background: #fff;
  }
  .m-row .dot.busy {
    background: var(--el-color-primary);
    border-color: var(--el-color-primary);
  }
  .m-row .dot.wait {
    background: var(--el-color-warning);
    border-color: var(--el-color-warning);
  }
  .m-row .who {
    flex: 1 1 auto;
    min-width: 0;
  }
  .m-row .n {
    font-size: 13px;
    color: var(--el-text-color-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .m-row .s {
    font-size: 11px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* 左栏：成员 / 任务 两个页签 */
  .roster-tabs {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .roster-tabs .el-tabs__header {
    margin: 0 0 8px;
  }
  .roster-tabs .el-tabs__nav-wrap::after {
    height: 1px;
    background: var(--el-border-color-lighter);
  }
  .roster-tabs .el-tabs__item {
    height: 30px;
    padding: 0 10px;
    font-size: 13px;
    line-height: 30px;
  }
  .roster-tabs .el-tabs__content {
    display: flex;
    flex: 1 1 auto;
    min-height: 0;
  }
  .roster-tabs .el-tab-pane {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
    min-height: 0;
  }
  .tb-badge {
    margin-left: 4px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    font-size: 10.5px;
  }
  .roster-foot {
    margin-top: auto;
    padding-top: 6px;
    border-top: 1px solid var(--el-border-color-lighter);
    font-size: 12px;
  }
  .roster-foot .link {
    color: var(--el-color-primary);
    cursor: pointer;
  }
  .roster-foot .link:hover {
    text-decoration: underline;
  }

  /* 任务列表（一次派活一条） */
  .task-tools {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .task-tools .ttl {
    font-weight: 600;
    color: var(--el-text-color-regular);
  }
  .task-tools {
    gap: 6px;
  }
  .task-tools .task-date {
    flex: 1 1 auto;
    min-width: 0;
  }
  .task-tools .task-date .el-input__wrapper {
    padding: 0 8px;
  }
  .task-filters {
    display: flex;
    gap: 6px;
  }
  .task-filters .f-status {
    flex: 0 0 96px;
  }
  .task-filters .f-agent {
    flex: 1 1 auto;
    min-width: 0;
  }
  .run-strip .it.clickable {
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 4px;
  }
  .run-strip .it.clickable:hover {
    background: var(--el-fill-color-light);
  }
  .run-strip .it.on {
    background: var(--el-color-primary-light-9);
  }
  .task-pager {
    flex: 0 0 auto;
    display: flex;
    justify-content: center;
    padding-top: 6px;
    border-top: 1px solid var(--el-border-color-lighter);
  }
  .task-pager .el-pagination {
    --el-pagination-button-width: 22px;
    --el-pagination-button-height: 22px;
    --el-pagination-font-size: 11px;
  }
  .task-list {
    flex: 1 1 auto;
    min-height: 0;
    margin: 0 -6px;
    padding: 0 6px;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .task-list::-webkit-scrollbar {
    width: 6px;
  }
  .task-list::-webkit-scrollbar-thumb {
    border-radius: 3px;
    background: var(--el-border-color);
  }
  .t-row {
    display: flex;
    gap: 7px;
    padding: 7px 6px;
    border-radius: 4px;
    cursor: pointer;
  }
  .t-row:hover {
    background: var(--el-fill-color-lighter);
  }
  .t-row.on {
    background: var(--el-color-primary-light-9);
  }
  .t-dot {
    flex: 0 0 6px;
    width: 6px;
    height: 6px;
    margin-top: 6px;
    border-radius: 50%;
    background: var(--el-text-color-placeholder);
  }
  .t-dot.ok {
    background: var(--el-color-success);
  }
  .t-dot.error {
    background: var(--el-color-danger);
  }
  .t-dot.running {
    background: var(--el-color-warning);
  }
  .t-main {
    flex: 1 1 auto;
    min-width: 0;
  }
  .t-p {
    display: -webkit-box;
    overflow: hidden;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--el-text-color-primary);
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
  }
  .t-m {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 2px;
    font-size: 11px;
    color: var(--el-text-color-placeholder);
  }

  /* 右：舞台 */
  .office-stage-card {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--el-border-color-light);
    border-radius: 4px;
    overflow: hidden;
  }
  .office-stage-card :deep(.el-card__body) {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 0;
  }
  .stage {
    position: relative;
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
    background: #f1f1f1;
    cursor: grab;
  }
  .stage:active {
    cursor: grabbing;
  }
  .stage {
    transition: background-color 0.5s ease;
  }
  .plates {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  /* 人名牌 */
  .ag-chip {
    position: absolute;
    transform: translate(-50%, -100%);
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 3px 7px 3px 6px;
    background: #fff;
    border: 1px solid var(--el-border-color-light);
    border-radius: 5px;
    box-shadow: 0 2px 6px rgba(31, 39, 51, 0.1);
    white-space: nowrap;
    pointer-events: auto;
    cursor: pointer;
    font-size: 10.5px;
    max-width: 208px;
    padding: 2px 6px 2px 5px;
  }
  .ag-chip.sel {
    border-color: var(--el-color-primary);
    box-shadow: 0 3px 10px rgba(64, 158, 255, 0.25);
  }
  .ag-chip.hov {
    border-color: #a0cfff;
  }
  .ag-chip.wait {
    border-color: #f3d19e;
    background: #fffdf9;
  }
  .ag-chip.err {
    border-color: var(--el-color-danger-light-5);
    background: #fffafa;
  }
  .ag-chip .dot.err {
    background: var(--el-color-danger);
    border-color: var(--el-color-danger);
  }
  .ag-chip .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    border: 1.4px solid #cdd3dc;
    background: #fff;
  }
  .ag-chip .dot.busy {
    background: var(--el-color-primary);
    border-color: var(--el-color-primary);
  }
  .ag-chip .dot.wait {
    background: var(--el-color-warning);
    border-color: var(--el-color-warning);
  }
  .ag-chip .nm {
    font-weight: 600;
    color: var(--el-text-color-primary);
    flex: 0 0 auto;
    max-width: 84px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* 对话气泡（组长派活 / 组员回话） */
  .ag-say {
    position: absolute;
    transform: translate(-50%, -100%);
    max-width: 218px;
    padding: 4px 8px;
    background: #2f3b4d;
    color: #fff;
    border-radius: 7px;
    font-size: 11px;
    line-height: 1.4;
    white-space: normal;
    word-break: break-word;
    box-shadow: 0 4px 12px rgba(20, 30, 45, 0.22);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.18s ease;
    z-index: 3;
  }
  .ag-say.on {
    opacity: 1;
  }
  .ag-say::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: -3.5px;
    width: 7px;
    height: 7px;
    margin-left: -3.5px;
    background: inherit;
    transform: rotate(45deg);
    border-radius: 1px;
  }
  .ag-say.dl {
    background: var(--el-color-primary);
  }
  .ag-say .who {
    display: block;
    font-style: normal;
    font-size: 10px;
    opacity: 0.85;
    margin-bottom: 1px;
  }

  .ag-chip .vis {
    font-style: normal;
    font-size: 10px;
    padding: 0 4px;
    border-radius: 3px;
    color: var(--el-color-primary);
    background: rgba(64, 158, 255, 0.12);
  }

  .ag-chip .late {
    font-style: normal;
    font-size: 10px;
    padding: 0 4px;
    border-radius: 3px;
    color: var(--el-color-danger);
    background: rgba(245, 108, 108, 0.12);
  }

  .roster-head .c {
    margin-left: 6px;
  }
  .roster-head .brief {
    margin-left: auto;
    color: var(--el-color-primary);
    font-size: 12px;
    cursor: pointer;
  }
  .roster-head .brief:hover {
    text-decoration: underline;
  }
  /* 加班 / 忙到冒烟 */
  .ag-chip .ot {
    font-style: normal;
    font-size: 10px;
    padding: 0 4px;
    border-radius: 3px;
    color: var(--el-color-warning);
    background: rgba(230, 162, 60, 0.12);
  }
  .ag-chip .hot {
    font-style: normal;
    font-size: 10px;
    padding: 0 4px;
    border-radius: 3px;
    color: #e6542b;
    background: rgba(230, 84, 43, 0.12);
    animation: hot-pulse 1.2s ease-in-out infinite;
  }
  @keyframes hot-pulse {
    0%,
    100% {
      opacity: 0.72;
    }
    50% {
      opacity: 1;
    }
  }

  .ag-chip .rl {
    color: var(--el-text-color-placeholder);
  }
  .ag-chip .tk {
    color: var(--el-color-primary);
    flex: 1 1 auto;
    min-width: 0;
    max-width: 132px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* 质检室上方的"待你确认"角标 */
  .room-badge {
    position: absolute;
    transform: translate(-50%, -100%);
    display: flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 12px;
    background: #fffdf9;
    border: 1px solid #f5dcb7;
    color: #b8802c;
    font-size: 11.5px;
    font-weight: 500;
    white-space: nowrap;
    box-shadow: 0 2px 10px rgba(230, 162, 60, 0.18);
    pointer-events: none;
  }

  /* 脚下状态点：默认只显示这个，名牌按需展开 */
  .ag-dot {
    position: absolute;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    background: #fff;
    border: 1.5px solid #c3ccd9;
    box-shadow: 0 1px 3px rgba(31, 39, 51, 0.22);
    pointer-events: none;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
  }
  .ag-dot.busy {
    background: var(--el-color-primary);
    border-color: var(--el-color-primary);
  }
  .ag-dot.wait {
    background: var(--el-color-warning);
    border-color: var(--el-color-warning);
  }
  .ag-dot.err,
  .ag-dot.error {
    background: var(--el-color-danger);
    border-color: var(--el-color-danger);
  }
  .ag-dot.hov {
    transform: translate(-50%, -50%) scale(1.45);
  }
  .ag-dot.sel {
    box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.28);
  }

  /* 3D 上下文丢失遮罩：盖住舞台，别让人对着黑屏猜 */
  .gl-lost {
    position: absolute;
    inset: 0;
    z-index: 8;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background: rgba(255, 255, 255, 0.86);
    backdrop-filter: blur(2px);
    text-align: center;
    padding: 20px;
  }
  .gl-lost .t {
    font-size: var(--el-font-size-medium);
    color: var(--el-text-color-primary);
    font-weight: 600;
  }
  .gl-lost .d {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    max-width: 420px;
    line-height: 1.6;
  }

  .people-hint {
    position: absolute;
    left: 50%;
    top: 12px;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 14px;
    background: rgba(64, 158, 255, 0.1);
    border: 1px solid rgba(64, 158, 255, 0.28);
    color: var(--el-color-primary);
    font-size: 12px;
    pointer-events: none;
    z-index: 5;
  }
  .people-hint .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-color-primary);
    animation: wrap-pulse 1.1s ease-in-out infinite;
  }

  .wrap-hint {
    position: absolute;
    left: 12px;
    top: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 14px;
    background: rgba(64, 158, 255, 0.1);
    border: 1px solid rgba(64, 158, 255, 0.28);
    color: var(--el-color-primary);
    font-size: 12px;
    pointer-events: none;
  }
  .wrap-hint .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-color-primary);
    animation: wrap-pulse 1.1s ease-in-out infinite;
  }
  @keyframes wrap-pulse {
    0%,
    100% {
      opacity: 0.35;
      transform: scale(0.8);
    }
    50% {
      opacity: 1;
      transform: scale(1);
    }
  }
  .stage-empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(247, 248, 250, 0.72);
    backdrop-filter: blur(1px);
  }

  .stage-foot {
    flex: 0 0 44px;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 0 14px;
    border-top: 1px solid var(--el-border-color-lighter);
    font-size: 11.5px;
    color: var(--el-text-color-secondary);
  }
  .stage-foot .legend {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .stage-foot .d {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    border: 1.4px solid var(--el-border-color-darker);
    background: transparent;
  }
  .stage-foot .d.busy {
    background: var(--el-color-primary);
    border-color: var(--el-color-primary);
  }
  .stage-foot .d.wait {
    background: var(--el-color-warning);
    border-color: var(--el-color-warning);
  }
  .stage-foot .spacer {
    flex: 1 1 auto;
  }
  .stage-foot .tip {
    color: var(--el-text-color-placeholder);
    font-size: 11px;
  }

  /* 顶部常驻统计条 */
.of-stats {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  margin: 0 0 8px;
  padding: 6px 12px;
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
  font-size: 12px;
}
.of-stats .it b {
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.of-stats .it.bad b {
  color: var(--el-color-danger);
}
.of-stats .spacer {
  flex: 1 1 auto;
}
.of-stats .more {
  color: var(--el-color-primary);
  cursor: pointer;
}
.of-stats .more:hover {
  text-decoration: underline;
}

/* 连接断开提示条：常驻，直到用户处理 */
.conn-lost {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 8px;
  padding: 8px 12px;
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
}
.conn-lost .t {
  color: var(--el-color-danger);
  font-weight: 600;
}
.conn-lost .d {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.conn-lost .spacer {
  flex: 1 1 auto;
}
.conn-lost .of-btn {
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid var(--el-color-danger-light-5);
  background: var(--el-bg-color);
  color: var(--el-color-danger);
  cursor: pointer;
  font-size: 12px;
}
.conn-lost .of-btn:hover {
  background: var(--el-color-danger-light-8);
}

/* 任务列表里的失败原因（单行省略，悬停看全文） */
.tl-item .tl-e {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--el-color-danger);
}

/* 任务列表里的「重试」 */
.tl-item .tl-retry {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  cursor: pointer;
}
.tl-item .tl-retry:hover {
  background: var(--el-color-danger-light-7);
}

/* 名牌上的协同标记：受命于谁 / 组长在等谁 */
.ag-chip .hb {
  font-size: 12px;
  padding: 0 4px;
  border-radius: 3px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.ag-chip .hb.wt {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

/* 名牌上的定时任务标记：到点自己跑起来，不是人派的，用暖色区分 */
.ag-chip .cron {
  font-size: 12px;
  font-style: normal;
  padding: 0 4px;
  border-radius: 3px;
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

/* 执行过程里的时间戳：让"谁先谁后"一眼看出来 */
.of-trace .tm {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}

/* 最近执行流水条 */
  .brief-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-top: 1px solid var(--el-border-color-lighter);
    background: var(--el-color-primary-light-9);
    color: var(--el-text-color-regular);
    font-size: 12px;
  }
  .brief-bar .cap {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex: 0 0 auto;
    color: var(--el-color-primary);
    font-weight: 600;
  }
  .brief-bar .cap .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-color-primary);
  }
  .brief-bar .txt {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .run-strip {
    flex: 0 0 42px;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 0 14px;
    border-top: 1px solid var(--el-border-color-lighter);
    background: var(--el-fill-color-blank);
    font-size: 11.5px;
    color: var(--el-text-color-secondary);
    overflow: hidden;
  }
  .run-strip .cap {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
    color: var(--el-text-color-placeholder);
  }
  .run-strip .live {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--el-color-primary);
    box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.14);
  }
  .run-strip .it {
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  .run-strip .it em {
    font-style: normal;
    color: var(--el-text-color-primary);
    font-weight: 500;
  }
  .run-strip .it .u {
    color: var(--el-text-color-placeholder);
  }
  .run-strip .it .res {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--el-color-success);
  }
  .run-strip .it .res.error {
    background: var(--el-color-danger);
  }
  .run-strip .it time {
    color: var(--el-text-color-placeholder);
    font-variant-numeric: tabular-nums;
  }
  .run-strip .it.muted {
    color: var(--el-text-color-placeholder);
  }
  .run-strip .spacer {
    flex: 1 1 auto;
  }
  .run-strip .more {
    flex: 0 0 auto;
    color: var(--el-color-primary);
    cursor: pointer;
  }

  /* 详情抽屉 */
}


/* 今日简报弹窗（append-to-body，所以不能嵌在 .ai-office-page 里） */
.sum-top {
  margin-top: 12px;
}
.sum-top .cap {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.sum-top .row {
  display: grid;
  grid-template-columns: 104px 1fr 28px;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 12px;
}
.sum-top .row .n {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sum-top .row .el-progress {
  min-width: 0;
}
.sum-top .row .c {
  text-align: right;
  color: var(--el-text-color-secondary);
}

/* ================= 工具栏：选中某人后的「派给他」标记 ================= */
.picked {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.picked .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  border: 1.4px solid currentColor;
  background: transparent;
}
.picked .dot.busy {
  background: currentColor;
}
.picked .dot.wait {
  border-color: var(--el-color-warning);
}
.picked b {
  font-weight: 400;
  opacity: 0.65;
}
.picked:hover b {
  opacity: 1;
}
/* 形象编辑弹层（popover 会被 teleport 到 body，所以放顶层） */
.look-editor {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.look-editor .ln {
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.look-editor .sw {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.look-editor .dot {
  width: 20px;
  height: 20px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
}
.look-editor .dot:hover {
  border-color: var(--el-color-primary);
}
.look-editor .chip {
  padding: 2px 9px;
  border: 1px solid var(--el-border-color);
  border-radius: 999px;
  background: transparent;
  color: var(--el-text-color-regular);
  font-size: 12px;
  cursor: pointer;
}
.look-editor .chip.on {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
/* 执行过程时间线（对话式，紧凑） */
.steps-panel {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 7;
  display: flex;
  flex-direction: column;
  width: 356px;
  max-height: 78%;
  overflow: hidden;
  background: var(--el-bg-color-overlay);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(31, 39, 51, 0.14);
}
.steps-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.steps-head .live {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-primary);
  animation: wrap-pulse 1.1s ease-in-out infinite;
}
.steps-head .t {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.steps-head .mem {
  padding: 0 5px;
  border-radius: 3px;
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
  font-size: 10.5px;
  line-height: 16px;
}
.steps-head .c {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.steps-body {
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px 10px 10px;
  mask-image: linear-gradient(to bottom, transparent 0, #000 8px, #000 calc(100% - 8px), transparent 100%);
}
/* 细滚动条：面板窄，默认滚动条太抢眼 */
.steps-body::-webkit-scrollbar {
  width: 6px;
}
.steps-body::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: var(--el-border-color);
}
.steps-body::-webkit-scrollbar-track {
  background: transparent;
}
.steps-body .blk {
  position: relative;
  margin-bottom: 5px;
  padding: 6px 8px 7px;
  border-left: 3px solid var(--el-color-primary);
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.055);
  cursor: pointer;
  transition: background-color 0.15s ease;
}
/* 相邻两块之间补一段竖线：整条 trace 读起来是一根连续的时间轴 */
.steps-body .blk + .blk::before {
  content: "";
  position: absolute;
  top: -7px;
  left: 0;
  width: 3px;
  height: 7px;
  background: rgba(59, 130, 246, 0.25);
}
.steps-body .blk.tool + .blk::before,
.steps-body .blk.tool::before {
  background: rgba(139, 92, 246, 0.25);
}
.steps-body .blk.reply::before,
.steps-body .blk.tool + .blk::before {
  background: rgba(16, 185, 129, 0.25);
}
.steps-body .blk.summary::before,
.steps-body .blk.summary + .blk::before {
  background: rgba(230, 162, 60, 0.28);
}
.steps-body .blk:hover {
  background: rgba(59, 130, 246, 0.085);
}
.steps-body .blk.tool {
  border-left-color: #8b5cf6;
  background: rgba(139, 92, 246, 0.06);
}
.steps-body .blk.reply {
  border-left-color: #10b981;
  background: rgba(16, 185, 129, 0.06);
}
.steps-body .blk.summary {
  border-left-color: #e6a23c;
  background: rgba(230, 162, 60, 0.07);
}
.steps-body .blk.error {
  border-left-color: #e6542b;
  background: rgba(230, 84, 43, 0.07);
}
.steps-body .blk .hd {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.steps-body .blk .who-dot {
  flex: 0 0 6px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 1px;
}
/* 多次工具：名字排成药丸，一行放下最多的信息 */
.steps-body .blk .pills {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 4px;
  min-width: 0;
  max-height: 32px;
  overflow: hidden;
}
.steps-body .blk .tool.count {
  flex: 0 0 auto;
}
.steps-body .blk .pill {
  flex: 0 0 auto;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--el-fill-color-light);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 10px;
  line-height: 14px;
  color: var(--el-text-color-secondary);
}
/* 合并块展开后的逐条调用 */
.steps-body .blk .calls {
  margin-top: 4px;
}
.steps-body .blk .call + .call {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.steps-body .blk .call-hd {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}
.steps-body .blk .tool.sm {
  padding: 0;
  background: transparent;
  font-size: 10.5px;
  color: #7c3aed;
}
.steps-body .blk .call-arg {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.steps-body .blk .rs-inline {
  max-height: 84px;
  margin-top: 2px;
  padding-left: 6px;
  overflow-y: auto;
  border-left: 2px solid var(--el-border-color);
  color: var(--el-text-color-secondary);
}
.steps-body .blk .who {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}
.steps-body .blk .dot-sep {
  color: var(--el-text-color-placeholder);
}
.steps-body .blk .tool {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(139, 92, 246, 0.1);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 10.5px;
  line-height: 15px;
  color: #7c3aed;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.steps-body .blk .to {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.steps-body .blk .bd {
  display: -webkit-box;
  margin: 2px 0 0;
  overflow: hidden;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.steps-body .blk .bd.plain {
  color: var(--el-text-color-secondary);
}
.steps-body .blk .bd.code {
  padding: 5px 7px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  font-family: ui-monospace, Consolas, monospace;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.steps-body .blk .rs {
  margin-top: 6px;
  padding-left: 8px;
  border-left: 2px solid var(--el-border-color);
}
.steps-body .blk .rs .bd {
  margin-top: 0;
  color: var(--el-text-color-secondary);
  -webkit-line-clamp: 2;
}
.steps-body .blk.open .bd {
  display: block;
  max-height: 160px;
  overflow-y: auto;
  -webkit-line-clamp: unset;
}

/* ================================================================
   办公室自绘皮肤（这一页不再套 Element Plus 的卡片/表单外观）
   来源：场景里的木头、黄铜、图纸 —— 暖纸底 + 橡木强调 + 等宽数字
   ================================================================ */
.ai-office-page {
  --of-paper: #fcfbf8;
  --of-paper2: #f6f3ec;
  --of-line: #e6e0d4;
  --of-line2: #efeade;
  --of-ink: #2e2a24;
  --of-ink2: #6f685d;
  --of-ink3: #9a9285;
  --of-oak: #b07d3f;
  --of-oak-soft: #f3e8d6;
  --of-busy: #3f7f6b;
  --of-err: #b4543f;
  --of-wait: #c08a33;
  --of-mono: ui-monospace, "SFMono-Regular", Consolas, monospace;
  background: #efece5;
  padding: 12px;
}

/* 两块底板：暖纸、1px 暖灰线、内高光 */
.ai-office-page .office-roster,
.ai-office-page .office-stage-card {
  background: var(--of-paper);
  border: 1px solid var(--of-line);
  border-radius: 10px;
  box-shadow: inset 0 1px 0 #fff;
}
.ai-office-page .office-roster {
  flex: 0 0 232px;
  width: 232px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px;
}
.ai-office-page .office-body {
  gap: 10px;
}
.ai-office-page .office-bar {
  background: var(--of-paper);
  border-bottom: 1px solid var(--of-line2);
}
.ai-office-page .office-bar .el-input__wrapper {
  background: var(--of-paper2);
  border-radius: 7px;
  box-shadow: inset 0 0 0 1px var(--of-line);
}
.ai-office-page .office-bar .el-button {
  border-color: var(--of-line);
  border-radius: 7px;
  background: var(--of-paper);
  color: var(--of-ink2);
}
.ai-office-page .office-bar .el-button--primary {
  border-color: #9c6d34;
  background: var(--of-oak);
  color: #fff;
}
.ai-office-page .office-bar .el-button-group .el-button--primary {
  background: var(--of-oak-soft);
  border-color: #d9c3a1;
  color: #7d5522;
}

/* ---------- 页签（自绘） ---------- */
.of-tabs {
  display: flex;
  gap: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--of-line2);
}
.of-tab {
  position: relative;
  padding: 0 0 7px;
  border: 0;
  background: transparent;
  color: var(--of-ink3);
  font-size: 13px;
  cursor: pointer;
}
.of-tab.on {
  color: var(--of-ink);
  font-weight: 600;
}
.of-tab.on::after {
  content: "";
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: var(--of-oak);
}
.of-tab .n {
  margin-left: 3px;
  font-family: var(--of-mono);
  font-size: 10.5px;
  color: var(--of-ink3);
}

/* ---------- 左栏：成员 ---------- */
.of-stat {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 8px 2px 0;
  font-size: 11.5px;
  color: var(--of-ink3);
}
.of-stat b {
  font-family: var(--of-mono);
  font-weight: 600;
  color: var(--of-ink);
}
.of-stat .warn {
  color: var(--of-wait);
}
.of-stat .pending {
  cursor: pointer;
}
.of-stat .pending:hover {
  text-decoration: underline;
}
.of-input {
  flex: 0 0 auto;
  height: 26px;
  margin-top: 8px;
  padding: 0 8px;
  border: 1px solid var(--of-line);
  border-radius: 6px;
  background: var(--of-paper2);
  color: var(--of-ink);
  font-size: 12px;
  outline: none;
}
.of-input::placeholder {
  color: var(--of-ink3);
}
.of-input:focus {
  border-color: var(--of-oak);
  background: var(--of-paper);
}
.of-list {
  flex: 1 1 auto;
  min-height: 0;
  margin: 8px -4px 0;
  padding: 0 4px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.of-list::-webkit-scrollbar {
  width: 6px;
}
.of-list::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: #ded7c9;
}
.of-list::-webkit-scrollbar-track {
  background: transparent;
}
.of-empty {
  padding: 26px 6px;
  color: var(--of-ink3);
  font-size: 12px;
  text-align: center;
}
/* 舞台里的空态 / 3D 失败兜底 */
.of-empty-block {
  max-width: 360px;
  padding: 18px 20px;
  border: 1px solid var(--of-line);
  border-radius: 10px;
  background: var(--of-paper);
  box-shadow: 0 8px 22px rgba(90, 78, 58, 0.1);
  text-align: center;
}
.of-empty-block .t {
  margin-bottom: 6px;
  color: var(--of-ink);
  font-size: 13px;
  font-weight: 600;
}
.of-empty-block .d {
  margin-bottom: 10px;
  color: var(--of-ink3);
  font-size: 12px;
  line-height: 1.6;
}
.of-foot {
  flex: 0 0 auto;
  margin-top: 6px;
  padding-top: 7px;
  border-top: 1px solid var(--of-line2);
  font-size: 12px;
}
.of-foot .link {
  color: var(--of-oak);
  cursor: pointer;
}
.of-foot .link:hover {
  text-decoration: underline;
}

/* 成员行 */
.ai-office-page .office-roster .m-row {
  position: relative;
  gap: 9px;
  padding: 6px;
  border-radius: 7px;
}
.ai-office-page .office-roster .m-row:hover {
  background: var(--of-paper2);
}
.ai-office-page .office-roster .m-row.on {
  background: var(--of-oak-soft);
}
.ai-office-page .office-roster .m-row.on::before {
  content: "";
  position: absolute;
  top: 6px;
  bottom: 6px;
  left: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--of-oak);
}
.ai-office-page .m-row .m-av {
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border: 1px solid var(--of-line);
  border-radius: 50%;
  background: var(--of-paper2);
  color: var(--of-ink2);
  font-size: 11px;
  font-weight: 600;
}
.ai-office-page .m-row .m-av.busy {
  border-color: #bcd8cd;
  background: #e9f2ee;
  color: var(--of-busy);
  box-shadow: none;
}
.ai-office-page .m-row .m-av.error {
  border-color: #e2c0b8;
  background: #f7e9e5;
  color: var(--of-err);
  box-shadow: none;
}
.ai-office-page .m-row .n {
  font-size: 12.5px;
  color: var(--of-ink);
}
.ai-office-page .m-row .s {
  font-size: 11px;
  color: var(--of-ink3);
}
.ai-office-page .m-row .lead {
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--of-oak-soft);
  color: #7d5522;
  font-size: 10px;
  font-weight: 500;
}
.ai-office-page .m-row .st {
  margin-top: 3px;
  font-family: var(--of-mono);
  font-size: 10.5px;
  color: var(--of-ink3);
}
.ai-office-page .m-row .st.busy {
  color: var(--of-busy);
}
.ai-office-page .m-row .st.error {
  color: var(--of-err);
}
.ai-office-page .m-row .st.wait {
  color: var(--of-wait);
}

/* ---------- 左栏：任务 ---------- */
.of-dstep {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 9px;
}
.of-dstep .d {
  flex: 1 1 auto;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--of-line);
  border-radius: 6px;
  background: var(--of-paper2);
  color: var(--of-ink2);
  font-family: var(--of-mono);
  font-size: 11.5px;
}
.of-ico {
  flex: 0 0 24px;
  width: 24px;
  height: 26px;
  border: 1px solid var(--of-line);
  border-radius: 6px;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.of-ico:hover:not(:disabled) {
  border-color: var(--of-oak);
  color: var(--of-oak);
}
.of-ico:disabled {
  opacity: 0.4;
  cursor: default;
}
.of-mini {
  height: 26px;
  padding: 0 8px;
  border: 1px solid var(--of-line);
  border-radius: 6px;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 11.5px;
  cursor: pointer;
}
.of-mini:hover {
  border-color: var(--of-oak);
  color: var(--of-oak);
}
.of-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-top: 7px;
}
.of-chip {
  padding: 2px 7px;
  border: 1px solid var(--of-line);
  border-radius: 999px;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 10.5px;
  cursor: pointer;
}
.of-chip.on {
  border-color: #d9c3a1;
  background: var(--of-oak-soft);
  color: #7d5522;
  font-weight: 600;
}
.of-select {
  flex: 1 1 auto;
  min-width: 0;
  height: 22px;
  padding: 0 4px;
  border: 1px solid var(--of-line);
  border-radius: 999px;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 10.5px;
  outline: none;
}
.of-pager {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 6px;
  padding-top: 7px;
  border-top: 1px solid var(--of-line2);
  color: var(--of-ink2);
  font-family: var(--of-mono);
  font-size: 11px;
}
.of-pager b {
  color: var(--of-ink);
}
.of-pager .of-ico {
  height: 22px;
  flex-basis: 22px;
}

/* 任务行 */
.ai-office-page .t-row {
  gap: 7px;
  padding: 6px;
  border-radius: 7px;
}
.ai-office-page .t-row:hover {
  background: var(--of-paper2);
}
.ai-office-page .t-row.on {
  background: var(--of-oak-soft);
}
.ai-office-page .t-dot {
  width: 6px;
  height: 6px;
  margin-top: 6px;
  background: var(--of-ink3);
}
.ai-office-page .t-dot.ok {
  background: var(--of-busy);
}
.ai-office-page .t-dot.error {
  background: var(--of-err);
}
.ai-office-page .t-dot.running {
  background: var(--of-wait);
}
.ai-office-page .t-p {
  font-size: 12px;
  line-height: 1.4;
  color: var(--of-ink);
}
.ai-office-page .t-m {
  margin-top: 2px;
  font-family: var(--of-mono);
  font-size: 10.5px;
  color: var(--of-ink3);
}

/* ---------- 右：执行过程（分支树） ---------- */
/* 定时任务提示条：贴在舞台底部中间，点一下看这一轮的执行过程 */
.cron-hint {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 78%;
  padding: 5px 12px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--el-border-color);
  box-shadow: 0 2px 10px rgba(31, 45, 61, 0.08);
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  z-index: 6;
}
.cron-hint:hover {
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}
.cron-hint .bell {
  font-size: 13px;
}
.cron-hint .nm {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-primary);
  font-weight: 600;
}
.cron-hint .st {
  padding: 0 6px;
  border-radius: 8px;
  line-height: 18px;
}
.cron-hint .st.live {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  animation: cron-blink 1.4s ease-in-out infinite;
}
.cron-hint .st.good {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.cron-hint .st.bad {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.cron-hint .who {
  color: var(--el-text-color-secondary);
}
@keyframes cron-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

.of-trace {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 7;
  display: flex;
  flex-direction: column;
  width: 352px;
  max-height: calc(100% - 20px);
  overflow: hidden;
  border: 1px solid var(--of-line);
  border-radius: 10px;
  background: rgba(252, 251, 248, 0.97);
  box-shadow: 0 10px 24px rgba(90, 78, 58, 0.14);
}
.of-thead {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border-bottom: 1px solid var(--of-line2);
}
.of-thead .t {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--of-ink);
}
.of-thead .live {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--of-oak);
  animation: of-pulse 1.1s ease-in-out infinite;
}
@keyframes of-pulse {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
.of-thead .mem {
  padding: 0 5px;
  border-radius: 3px;
  background: #eaf3ee;
  color: var(--of-busy);
  font-size: 10px;
}
.of-thead .c {
  margin-left: auto;
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-size: 10.5px;
}
.of-tbody {
  flex: 1 1 auto;
  min-height: 0;
  padding: 9px 11px 11px;
  overflow-y: auto;
  overscroll-behavior: contain;
  mask-image: linear-gradient(to bottom, transparent 0, #000 6px, #000 calc(100% - 6px), transparent 100%);
}
.of-tbody::-webkit-scrollbar {
  width: 6px;
}
.of-tbody::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: #ded7c9;
}
.of-root {
  display: flex;
  gap: 7px;
  align-items: flex-start;
}
.of-root .bul {
  flex: 0 0 7px;
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--of-ink);
}
.of-root .ttl {
  color: var(--of-ink);
  font-size: 12.5px;
  font-weight: 600;
}
.of-root .ask {
  margin-top: 2px;
  color: var(--of-ink2);
  font-size: 11.5px;
  line-height: 1.45;
}
.of-branch {
  position: relative;
  margin: 6px 0 0 3px;
  padding-left: 14px;
  border-left: 1px solid #ddd4c2;
}
.of-branch::before {
  content: "";
  position: absolute;
  top: 14px;
  left: 0;
  width: 10px;
  height: 1px;
  background: #ddd4c2;
}
.of-branch .bhead {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0 4px;
}
.of-branch .who-dot {
  flex: 0 0 6px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--of-oak);
}
.of-branch .n {
  color: var(--of-ink);
  font-size: 12px;
  font-weight: 600;
}
.of-branch .cnt {
  padding: 0 4px;
  border-radius: 3px;
  background: var(--of-paper2);
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-size: 10px;
}
.of-branch .tool {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  padding: 2px 0;
  cursor: pointer;
}
.of-branch .tool .k {
  padding: 0 4px;
  border-radius: 3px;
  background: #f4eefc;
  color: #8a5bbf;
  font-family: var(--of-mono);
  font-size: 10.5px;
}
.of-branch .tool .a {
  flex: 1 1 110px;
  min-width: 0;
  overflow: hidden;
  color: var(--of-ink3);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.of-branch .tool .r {
  color: var(--of-busy);
  font-family: var(--of-mono);
  font-size: 10.5px;
}
.of-branch .of-res {
  flex: 1 1 100%;
  max-height: 76px;
  margin: 2px 0 2px 2px;
  padding-left: 6px;
  overflow-y: auto;
  border-left: 2px solid var(--of-line);
  color: var(--of-ink3);
  font-size: 10.5px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}
.of-branch .say {
  margin-top: 4px;
  padding: 5px 7px;
  border-left: 2px solid #bcd8cd;
  border-radius: 6px;
  background: #f2f7f4;
  color: #2f5c4b;
  font-size: 11.5px;
  line-height: 1.5;
}
.of-sum {
  margin: 8px 0 0 3px;
  padding: 7px 9px;
  border-left: 3px solid var(--of-oak);
  border-radius: 7px;
  background: #fbf4e7;
}
.of-sum.err {
  border-left-color: var(--of-err);
  background: #fbeeea;
}
.of-sum .h {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
  color: var(--of-ink);
  font-size: 12px;
  font-weight: 600;
}
.of-sum .h .who-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.of-sum .x {
  color: #4a4238;
  font-size: 11.5px;
  line-height: 1.55;
}
.of-tfoot {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  padding: 6px 11px;
  border-top: 1px solid var(--of-line2);
  background: var(--of-paper2);
  color: var(--of-ink3);
  font-size: 10.5px;
}
.of-tfoot .lg {
  display: flex;
  align-items: center;
  gap: 4px;
}
.of-tfoot .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--of-busy);
}
.of-tfoot .dot.wait {
  background: var(--of-wait);
}
.of-tfoot .dot.err {
  background: var(--of-err);
}
.of-tfoot .sp {
  flex: 1 1 auto;
}


/* 底部流水条 / 图例：跟着暖色板走，别留 EP 的蓝 */
.ai-office-page .run-strip {
  border-top: 1px solid var(--of-line2);
  background: var(--of-paper);
  color: var(--of-ink3);
}
.ai-office-page .run-strip .live {
  background: var(--of-oak);
  box-shadow: 0 0 0 3px rgba(176, 125, 63, 0.14);
}
.ai-office-page .run-strip .it em {
  color: var(--of-ink);
}
.ai-office-page .run-strip .it .res {
  background: var(--of-busy);
}
.ai-office-page .run-strip .it .res.error {
  background: var(--of-err);
}
.ai-office-page .run-strip .more {
  color: var(--of-oak);
}
.ai-office-page .run-strip .it.on {
  background: var(--of-oak-soft);
}
.ai-office-page .stage-foot {
  border-top: 1px solid var(--of-line2);
  background: var(--of-paper);
  color: var(--of-ink3);
}
.ai-office-page .stage-foot .d.busy {
  background: var(--of-busy);
  border-color: var(--of-busy);
}
.ai-office-page .stage-foot .d.wait {
  background: var(--of-wait);
  border-color: var(--of-wait);
}
.ai-office-page .stage-foot .d {
  border-color: #c9c1b1;
}
/* 头像：圆一点、别被行高拉成椭圆 */
.ai-office-page .m-row .m-av {
  border-radius: 999px;
  line-height: 1;
  padding: 0;
}
/* 选中人名的胶囊 + 顶栏输入框统一暖色 */
.ai-office-page .picked {
  border-color: #d9c3a1;
  background: var(--of-oak-soft);
  color: #7d5522;
}
.ai-office-page .picked .dot {
  border-color: currentColor;
}


/* ---------- 顶栏（全自绘） ---------- */
.of-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
}
.of-bar-input {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 420px;
  margin-top: 0;
  height: 28px;
}
.of-btn {
  flex: 0 0 auto;
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--of-line);
  border-radius: 7px;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 12.5px;
  cursor: pointer;
}
.of-btn:hover:not(:disabled) {
  border-color: var(--of-oak);
  color: var(--of-oak);
}
.of-btn.primary {
  border-color: #9c6d34;
  background: var(--of-oak);
  color: #fff;
  font-weight: 600;
}
.of-btn.primary:hover:not(:disabled) {
  background: #a3722f;
  color: #fff;
}
.of-btn:disabled {
  opacity: 0.6;
  cursor: default;
}
/* 运行中的「停止」：砖红，避免和主按钮混淆 */
.of-btn.stop {
  border-color: #d8b3a8;
  background: #fbeeea;
  color: #b4543f;
  font-weight: 600;
}
.of-btn.stop:hover {
  border-color: #b4543f;
  background: #f7e3dd;
  color: #a04a36;
}
.of-gap {
  flex: 1 1 auto;
}
.of-seg {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--of-line);
  border-radius: 7px;
}
.of-seg button {
  height: 26px;
  padding: 0 10px;
  border: 0;
  background: var(--of-paper);
  color: var(--of-ink2);
  font-size: 12px;
  cursor: pointer;
}
.of-seg button[aria-pressed="true"] {
  background: var(--of-oak-soft);
  color: #7d5522;
  font-weight: 600;
}
.of-picked {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border: 1px solid #d9c3a1;
  border-radius: 999px;
  background: var(--of-oak-soft);
  color: #7d5522;
  font-size: 12px;
  cursor: pointer;
}
.of-picked .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  border: 1.4px solid currentColor;
}
.of-picked .dot.busy {
  background: currentColor;
}
.of-picked b {
  font-weight: 400;
  opacity: 0.6;
}
/* 「⋯」菜单（自绘） */
.of-more {
  position: relative;
  flex: 0 0 auto;
}
.of-menu {
  position: absolute;
  top: 32px;
  right: 0;
  z-index: 31;
  width: 172px;
  padding: 5px;
  border: 1px solid var(--of-line);
  border-radius: 9px;
  background: var(--of-paper);
  box-shadow: 0 12px 26px rgba(90, 78, 58, 0.16);
}
.of-menu button {
  display: block;
  width: 100%;
  padding: 7px 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--of-ink);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
}
.of-menu button:hover {
  background: var(--of-paper2);
}
.of-ico.lit {
  border-color: #d9c3a1;
  background: var(--of-oak-soft);
}

/* 改形象浮层 */
.of-pop-mask {
  position: fixed;
  inset: 0;
  z-index: 30;
}
.of-look {
  position: relative;
  flex: 0 0 auto;
}
.of-pop {
  position: absolute;
  top: 34px;
  right: 0;
  z-index: 31;
  width: 236px;
  padding: 10px;
  border: 1px solid var(--of-line);
  border-radius: 10px;
  background: var(--of-paper);
  box-shadow: 0 12px 28px rgba(90, 78, 58, 0.18);
}
.of-pop .ln {
  margin: 6px 0 4px;
  color: var(--of-ink3);
  font-size: 11px;
}
.of-pop .ln:first-child {
  margin-top: 0;
}
.of-pop .sw {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.of-pop .chip {
  padding: 2px 9px;
  border: 1px solid var(--of-line);
  border-radius: 999px;
  background: transparent;
  color: var(--of-ink2);
  font-size: 12px;
  cursor: pointer;
}
.of-pop .chip.on {
  border-color: var(--of-oak);
  background: var(--of-oak-soft);
  color: #7d5522;
}
.of-pop .dot {
  width: 20px;
  height: 20px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: 50%;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12);
}
.of-pop .dot:hover {
  border-color: var(--of-oak);
}

/* ---------- 成员行：迷你状态环 ---------- */
.ai-office-page .m-row .m-av {
  position: relative;
}
.ai-office-page .m-row .m-av::after {
  content: "";
  position: absolute;
  inset: -3px;
  border: 1.5px solid transparent;
  border-radius: 999px;
  transition: border-color 0.25s ease;
}
.ai-office-page .m-row .m-av.busy::after {
  border-color: rgba(63, 127, 107, 0.45);
  animation: of-ring 1.6s ease-in-out infinite;
}
.ai-office-page .m-row .m-av.error::after {
  border-color: rgba(180, 84, 63, 0.5);
}
.ai-office-page .m-row .m-av.wait::after {
  border-color: rgba(192, 138, 51, 0.45);
}
@keyframes of-ring {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.96);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

/* ---------- 任务：竖向时间轴 ---------- */
.of-tl {
  position: relative;
  margin-top: 8px;
}
.of-tl::before {
  content: "";
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 55px;
  width: 1px;
  background: #e3dccd;
}
.tl-item {
  position: relative;
  display: grid;
  grid-template-columns: 44px 10px 1fr;
  gap: 0 6px;
  align-items: start;
  width: 100%;
  padding: 6px 4px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.tl-item:hover {
  background: var(--of-paper2);
}
.tl-item.on {
  background: var(--of-oak-soft);
}
.tl-time {
  padding-top: 1px;
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-size: 10.5px;
}
.tl-dot {
  width: 7px;
  height: 7px;
  margin-top: 4px;
  margin-left: 1px;
  border: 1.5px solid var(--of-paper);
  border-radius: 50%;
  background: var(--of-ink3);
  box-shadow: 0 0 0 1px var(--of-ink3);
}
.tl-dot.ok {
  background: var(--of-busy);
  box-shadow: 0 0 0 1px var(--of-busy);
}
.tl-dot.error {
  background: var(--of-err);
  box-shadow: 0 0 0 1px var(--of-err);
}
.tl-dot.running {
  background: var(--of-wait);
  box-shadow: 0 0 0 1px var(--of-wait);
}
.tl-main {
  min-width: 0;
}
.tl-p {
  display: -webkit-box;
  overflow: hidden;
  color: var(--of-ink);
  font-size: 12px;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.tl-item.on .tl-p {
  font-weight: 600;
}
.tl-m {
  display: block;
  margin-top: 2px;
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-size: 10.5px;
}


/* ---------- 执行过程：支线依次长出来 ---------- */
@keyframes of-in {
  from {
    opacity: 0;
    transform: translateY(-5px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@keyframes of-grow {
  from {
    transform: scaleY(0);
  }
  to {
    transform: scaleY(1);
  }
}
.of-root {
  animation: of-in 0.26s ease-out both;
}
.of-branch {
  animation: of-in 0.3s ease-out both;
}
/* 竖线用伪元素画，才能从 0 长到 100% */
.of-branch {
  border-left: 0 !important;
}
.of-branch::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 1px;
  background: #ddd4c2;
  transform-origin: top;
  animation: of-grow 0.34s ease-out both;
}
.of-branch .tool {
  animation: of-in 0.22s ease-out both;
}
.of-branch .say {
  animation: of-in 0.24s ease-out both;
}
.of-sum {
  animation: of-in 0.3s ease-out both;
}
/* 场景里：被点名/调工具的人，工牌闪两下 */
@keyframes of-ping {
  0% {
    box-shadow: 0 0 0 0 rgba(176, 125, 63, 0.55);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(176, 125, 63, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(176, 125, 63, 0);
  }
}
.ag-chip.ping {
  animation: of-ping 0.7s ease-out 2;
  border-color: var(--of-oak, #b07d3f) !important;
}
/* 窄屏：上下堆叠（左栏压成一条，过程面板铺满舞台宽度） */
/* 只在真正的窄屏（手机/半屏窗口）才上下堆叠；电脑窗口缩到 1000 多 px 仍用左右布局 */
@media (max-width: 980px) {
  .ai-office-page .office-body {
    flex-direction: column;
  }
  .ai-office-page .office-roster {
    flex: 0 0 auto;
    width: 100%;
    max-height: 244px;
    padding: 8px 10px;
  }
  .ai-office-page .office-roster .of-list {
    max-height: 132px;
  }
  .ai-office-page .office-roster .of-foot {
    display: none;
  }
  .ai-office-page .of-trace {
    right: 10px;
    left: 10px;
    width: auto;
    max-height: 64%;
  }
  .ai-office-page .of-bar {
    flex-wrap: wrap;
    gap: 6px;
  }
  .ai-office-page .of-bar-input {
    flex: 1 1 180px;
    max-width: none;
  }
  .ai-office-page .stage-foot .tip {
    display: none;
  }
}


@media (prefers-reduced-motion: reduce) {
  .of-root,
  .of-branch,
  .of-branch::after,
  .of-branch .tool,
  .of-branch .say,
  .of-sum,
  .ag-chip.ping {
    animation: none !important;
  }
}


/* ===== 夜间：DOM 名牌/气泡跟着变暗，别在黑屋子里打白光 ===== */
.stage.night .ag-chip {
  background: rgba(26, 29, 35, 0.92);
  border-color: rgba(120, 132, 150, 0.32);
  color: #e7e5df;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.5);
}
.stage.night .ag-chip.sel {
  border-color: #b07d3f;
  box-shadow: 0 0 0 1px rgba(176, 125, 63, 0.5), 0 3px 12px rgba(0, 0, 0, 0.55);
}
.stage.night .ag-chip.hov {
  border-color: rgba(180, 190, 210, 0.5);
}
.stage.night .ag-chip .nm {
  color: #f2f0ea;
}
.stage.night .ag-chip .rl {
  color: #9aa1ad;
}
.stage.night .ag-chip .tk {
  color: #8fc3ff;
}
.stage.night .ag-chip .lead {
  background: rgba(176, 125, 63, 0.3);
  color: #eccb9f;
}
.stage.night .ag-chip .dot {
  background: transparent;
  border-color: #6b7280;
}
.stage.night .ag-chip .dot.busy {
  background: #59b79b;
  border-color: #59b79b;
}
.stage.night .ag-chip .dot.wait {
  background: #d9a24a;
  border-color: #d9a24a;
}
.stage.night .ag-chip .dot.err,
.stage.night .ag-chip .dot.error {
  background: #e0745c;
  border-color: #e0745c;
}
.stage.night .ag-dot {
  background: rgba(36, 40, 48, 0.85);
  border-color: rgba(200, 206, 216, 0.55);
  box-shadow: 0 1px 5px rgba(0, 0, 0, 0.65);
}
.stage.night .ag-say {
  background: #12151b;
  color: #e9e7e1;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.5);
}
.stage.night .ag-say.dl {
  background: #2a4a6b;
}
.stage.night .room-badge {
  background: rgba(42, 36, 26, 0.92);
  border-color: rgba(200, 160, 90, 0.4);
  color: #e6c894;
}
.stage.night .wrap-hint {
  background: rgba(28, 38, 50, 0.88);
  border-color: rgba(120, 170, 220, 0.32);
  color: #b9d6f2;
}

/* ================= 派活输入（自适应高度 + 最近任务） ================= */
.of-bar textarea.of-bar-input {
  height: auto;
  min-height: 28px;
  max-height: 92px;
  padding: 5px 8px;
  line-height: 1.45;
  font-family: inherit;
  resize: none;
  overflow-y: auto;
}
.of-recent {
  position: relative;
  flex: 0 0 auto;
}
.of-menu.recent {
  left: 0;
  right: auto;
  min-width: 260px;
  max-width: 360px;
  max-height: 220px;
  overflow-y: auto;
}
.of-menu.recent button {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ================= 镜头预设 ================= */
.cam-presets {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 8;
  display: flex;
  overflow: hidden;
  border: 1px solid var(--of-line);
  border-radius: 7px;
  background: rgba(252, 251, 248, 0.95);
  box-shadow: 0 2px 8px rgba(90, 78, 58, 0.1);
}
.cam-presets button {
  height: 24px;
  padding: 0 9px;
  border: 0;
  border-right: 1px solid var(--of-line2);
  background: transparent;
  color: var(--of-ink2);
  font-size: 11.5px;
  cursor: pointer;
}
.cam-presets button:last-child {
  border-right: 0;
}
.cam-presets button:hover {
  background: var(--of-paper2);
  color: var(--of-oak);
}
.cam-presets button.on {
  background: var(--of-oak);
  color: #fff;
  font-weight: 600;
}

/* ================= 首次引导 ================= */
.guide-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(28, 32, 40, 0.34);
}
.guide-card {
  width: 100%;
  max-width: 420px;
  padding: 16px 18px 12px;
  border: 1px solid var(--of-line);
  border-radius: 12px;
  background: var(--of-paper);
  box-shadow: 0 16px 40px rgba(40, 34, 24, 0.28);
}
.guide-card .g-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.guide-card .g-cap {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 3px;
  background: var(--of-paper2);
  color: var(--of-ink3);
  font-size: 10.5px;
  line-height: 17px;
}
.guide-card .g-t {
  font-size: 14px;
  font-weight: 600;
  color: var(--of-ink);
}
.guide-card .g-d {
  margin-top: 8px;
  color: var(--of-ink2);
  font-size: 12.5px;
  line-height: 1.7;
}
.guide-card .g-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}
.guide-card .dots {
  display: flex;
  gap: 5px;
}
.guide-card .dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--of-line);
}
.guide-card .dots i.on {
  background: var(--of-oak);
}
.guide-card .spacer {
  flex: 1 1 auto;
}

/* ================= 任务播报 ================= */
.cast-bar {
  position: relative;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-top: 1px solid var(--of-line2);
  background: var(--of-paper);
  font-size: 11.5px;
  color: var(--of-ink2);
}
.cast-bar .cap {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--of-ink3);
  font-size: 10.5px;
}
.cast-bar .cap .live {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--of-busy);
  animation: of-pulse 1.6s ease-in-out infinite;
}
.cast-bar .one {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.cast-bar .one em {
  margin-right: 5px;
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-style: normal;
  font-size: 10.5px;
}
.cast-bar .one .g,
.cast-list .c .g {
  margin-right: 5px;
  color: var(--of-oak);
  font-style: normal;
}
.cast-bar .one.bad,
.cast-list .c.bad {
  color: #b4543f;
}
.cast-bar .one.bad .g,
.cast-list .c.bad .g {
  color: #b4543f;
}
.cast-bar .bad-dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #d0674f;
}
.cast-list {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 32px;
  z-index: 12;
  max-height: 240px;
  padding: 6px 8px;
  overflow-y: auto;
  border: 1px solid var(--of-line);
  border-radius: 9px;
  background: rgba(252, 251, 248, 0.99);
  box-shadow: 0 10px 24px rgba(90, 78, 58, 0.16);
}
.cast-list .c {
  display: flex;
  align-items: baseline;
  gap: 2px;
  padding: 3px 2px;
  font-size: 11.5px;
  line-height: 1.5;
}
.cast-list .c + .c {
  border-top: 1px dashed var(--of-line2);
}
.cast-list .c em {
  flex: 0 0 auto;
  margin-right: 4px;
  color: var(--of-ink3);
  font-family: var(--of-mono);
  font-style: normal;
  font-size: 10.5px;
}
.cast-list .c .x {
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}
.cast-list .empty {
  padding: 10px;
  color: var(--of-ink3);
  font-size: 11.5px;
  text-align: center;
}

/* 小号文字按钮（复制结论 / 展开全部 / 播报展开） */
.of-linkbtn {
  flex: 0 0 auto;
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: var(--of-oak);
  font-size: 11px;
  cursor: pointer;
}
.of-linkbtn:hover {
  text-decoration: underline;
}

/* 「回到最新」：粘底被用户打断时出现 */
.of-jump {
  position: absolute;
  right: 14px;
  bottom: 40px;
  z-index: 8;
  height: 24px;
  padding: 0 10px;
  border: 1px solid var(--of-line);
  border-radius: 12px;
  background: rgba(252, 251, 248, 0.97);
  color: var(--of-oak);
  font-size: 11px;
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(90, 78, 58, 0.14);
}
.of-jump:hover {
  border-color: var(--of-oak);
}
.of-thead .spacer,
.of-sum .h .spacer {
  flex: 1 1 auto;
}

/* 空态示例任务 */
.of-samples {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  justify-content: center;
  margin-top: 10px;
}
.of-samples .lbl {
  color: var(--of-ink3);
  font-size: 11px;
}
.of-samples .sample {
  max-width: 100%;
  padding: 3px 8px;
  border: 1px dashed var(--of-line);
  border-radius: 10px;
  background: transparent;
  color: var(--of-ink2);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.of-samples .sample:hover {
  border-color: var(--of-oak);
  color: var(--of-oak);
}

</style>