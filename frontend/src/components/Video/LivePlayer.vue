<template>
  <div ref="playerRef" class="live-player" :class="{ 'is-loading': loading, 'has-error': !!error }">
    <video ref="videoRef" muted :poster="poster" autoplay playsinline class="player-video" />

    <div v-if="loading && !error" class="player-overlay connecting">
      <div class="loading-spinner" />
      <span>{{ loadingText }}</span>
    </div>

    <div v-if="error" class="player-overlay error" @click="handleRetry">
      <el-icon :size="20"><WarningFilled /></el-icon>
      <span>{{ error }}</span>
      <span class="retry-hint">点击重试</span>
    </div>

    <div class="player-info">
      <span class="protocol-badge" :class="currentType">{{ currentType || "?" }}</span>
      <span v-if="resolution" class="resolution-badge">{{ resolution }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, onMounted, nextTick } from "vue";

const props = withDefaults(
  defineProps<{
    streamUrl?: string;
    streamType?: "webrtc" | "flv" | "hls";
    streamId?: string;
    poster?: string;
  }>(),
  {
    streamUrl: "",
    streamType: "flv",
    streamId: "",
  }
);

const emit = defineEmits<{
  (e: "load"): void;
  (e: "error", msg: string): void;
}>();

const playerRef = ref<HTMLDivElement | null>(null);
const videoRef = ref<HTMLVideoElement | null>(null);
const loading = ref(false);
const loadingText = ref("连接中...");
const error = ref("");
const currentType = ref<string>("");
const resolution = ref("");

let playerInstance: any = null;
let pc: RTCPeerConnection | null = null;
let abortController: AbortController | null = null;

function destroyPlayer() {
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
  if (pc) {
    pc.close();
    pc = null;
  }
  if (playerInstance?.destroy) {
    playerInstance.destroy();
    playerInstance = null;
  }
  if (videoRef.value) {
    videoRef.value.src = "";
    videoRef.value.srcObject = null;
    videoRef.value.load();
  }
}

function buildStreamUrl(type: string): string {
  const streamId = props.streamId || "obs_test1";
  if (type === "flv") return `/live/${streamId}.live.flv`;
  if (type === "hls") return `/live/${streamId}/hls.m3u8`;
  if (type === "webrtc") return `webrtc://127.0.0.1:8000/rtc/live/${streamId}`;
  return props.streamUrl;
}

function playWebRTC() {
  currentType.value = "webrtc";
  loading.value = true;
  loadingText.value = "WebRTC 连接中...";
  error.value = "";

  pc = new RTCPeerConnection({
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" },
      { urls: "stun:stun1.l.google.com:19302" },
    ],
  });

  pc.addTransceiver("video", { direction: "recvonly" });
  pc.addTransceiver("audio", { direction: "recvonly" });

  const streamId = props.streamId || "obs_test1";

  pc.ontrack = (event) => {
    if (videoRef.value && event.streams[0]) {
      videoRef.value.srcObject = event.streams[0];
      loading.value = false;
      resolution.value = "";
      emit("load");
    }
  };

  pc.oniceconnectionstatechange = () => {
    if (pc?.iceConnectionState === "failed") {
      error.value = "WebRTC 连接失败";
      loading.value = false;
      emit("error", "WebRTC failed");
    }
  };

  pc.onicecandidate = (event) => {
    if (event.candidate === null) {
      const sdp = pc?.localDescription?.sdp;
      if (sdp) {
        abortController = new AbortController();
        fetch(`/api/v1/video/camera/webrtc/signaling`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ stream_id: streamId, sdp }),
          signal: abortController.signal,
        })
          .then((r) => r.json())
          .then((data) => {
            if (!abortController) return;
            if (data.code === 0 && data.sdp) {
              pc?.setRemoteDescription(
                new RTCSessionDescription({ type: "answer", sdp: data.sdp })
              );
              loading.value = false;
              emit("load");
            } else {
              error.value = `WebRTC 信令失败: ${data.msg || "unknown"}`;
              loading.value = false;
              emit("error", `WebRTC signaling: ${data.msg}`);
            }
          })
          .catch(() => {
            error.value = "WebRTC 信令请求失败";
            loading.value = false;
            emit("error", "WebRTC signaling error");
          });
      }
    }
  };

  pc.createOffer()
    .then((offer) => pc!.setLocalDescription(offer))
    .catch(() => {
      error.value = "WebRTC 创建 offer 失败";
      loading.value = false;
    });
}

function playFLV(url: string) {
  currentType.value = "flv";
  loading.value = true;
  loadingText.value = "FLV 连接中...";
  error.value = "";

  import("mpegts.js")
    .then((mpegtsModule) => {
      const mpegts = (mpegtsModule as any).default || mpegtsModule;
      if (mpegts.isSupported()) {
        playerInstance = mpegts.createPlayer(
          { type: "flv", url, isLive: true },
          {
            enableWorker: false,
            lazyLoad: false,
            stashInitialSize: 16,
            enableStashBuffer: false,
            liveBufferLatencyChasing: true,
          }
        );
        playerInstance.attachMediaElement(videoRef.value!);
        const onPlaying = () => {
          loading.value = false;
          emit("load");
        };
        videoRef.value!.addEventListener("playing", onPlaying, { once: true });
        playerInstance.load();
        playerInstance.play();
        setTimeout(onPlaying, 1200);
        playerInstance.on(mpegts.Events.ERROR, () => {
          error.value = "FLV 播放错误";
          loading.value = false;
          emit("error", "FLV error");
        });
      } else {
        playHLS(buildStreamUrl("hls"));
      }
    })
    .catch(() => {
      playHLS(buildStreamUrl("hls"));
    });
}

function playHLS(url: string) {
  currentType.value = "hls";
  loading.value = true;
  loadingText.value = "HLS 连接中...";
  error.value = "";

  import("hls.js")
    .then((hlsModule) => {
      const Hls = (hlsModule as any).default || hlsModule;
      if (Hls.isSupported()) {
        playerInstance = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
        });
        playerInstance.loadSource(url);
        playerInstance.attachMedia(videoRef.value!);
        playerInstance.on(Hls.Events.MANIFEST_PARSED, () => {
          loading.value = false;
          emit("load");
        });
        playerInstance.on(Hls.Events.ERROR, (_event: any, data: any) => {
          if (data.fatal) {
            error.value = "HLS 播放错误";
            loading.value = false;
            emit("error", "HLS error");
          }
        });
      } else if (videoRef.value?.canPlayType("application/vnd.apple.mpegurl")) {
        videoRef.value.src = url;
        loading.value = false;
        emit("load");
      } else {
        error.value = "浏览器不支持 HLS";
        loading.value = false;
        emit("error", "HLS unsupported");
      }
    })
    .catch(() => {
      error.value = "HLS 加载失败";
      loading.value = false;
    });
}

function play(url: string, forceType?: string) {
  destroyPlayer();
  error.value = "";
  loading.value = true;

  const type = forceType || props.streamType || "flv";

  if (type === "webrtc") {
    playWebRTC();
  } else if (type === "flv") {
    playFLV(buildStreamUrl("flv"));
  } else if (type === "hls") {
    playHLS(buildStreamUrl("hls"));
  } else {
    playFLV(buildStreamUrl("flv"));
  }
}

function switchProtocol(type: string) {
  if (type === currentType.value) return;
  play("", type);
}

function handleRetry() {
  play("", currentType.value || props.streamType);
}

onMounted(async () => {
  await nextTick();
  if (props.streamId) {
    play("", props.streamType);
  } else if (props.streamUrl) {
    play(props.streamUrl);
  }
});

watch(
  () => props.streamUrl,
  (val) => {
    if (val) play(val);
  }
);

watch(
  () => props.streamId,
  (id) => {
    if (id) play("", props.streamType);
  }
);

watch(
  () => props.streamType,
  (type) => {
    if (props.streamId && type) switchProtocol(type);
  }
);

onBeforeUnmount(() => {
  destroyPlayer();
});

defineExpose({ play, destroyPlayer, switchProtocol });
</script>

<style scoped>
.live-player {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #000;
}
.live-player.has-error {
  cursor: pointer;
}

.player-video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.player-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-top-color: var(--el-color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.player-overlay.error {
  color: var(--el-color-danger);
  cursor: pointer;
}
.retry-hint {
  font-size: 11px;
  color: var(--el-color-primary);
  opacity: 0;
  transition: opacity 0.2s;
}
.player-overlay.error:hover .retry-hint {
  opacity: 1;
}

.player-info {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 3;
  display: flex;
  gap: 4px;
  pointer-events: none;
}

.protocol-badge {
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-radius: 3px;
}
.protocol-badge.flv {
  color: #fff;
  background: rgba(64, 158, 255, 0.85);
}
.protocol-badge.hls {
  color: #fff;
  background: rgba(103, 194, 58, 0.85);
}
.protocol-badge.webrtc {
  color: #fff;
  background: rgba(230, 162, 60, 0.85);
}

.resolution-badge {
  padding: 1px 6px;
  font-size: 10px;
  color: #ccc;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 3px;
}
</style>
