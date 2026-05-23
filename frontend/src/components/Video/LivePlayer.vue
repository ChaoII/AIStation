<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps<{
  streamUrl?: string
  streamType?: 'webrtc' | 'flv' | 'hls'
  poster?: string
  autoplay?: boolean
}>()

const emit = defineEmits<{
  (e: 'load'): void
  (e: 'error', msg: string): void
}>()

const playerRef = ref<HTMLVideoElement | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
const loading = ref(false)
const error = ref('')
const currentType = ref<string>('')

let playerInstance: any = null
let pc: RTCPeerConnection | null = null

const playProtocols = ['webrtc', 'flv', 'hls']

function destroyPlayer() {
  if (pc) {
    pc.close()
    pc = null
  }
  if (playerInstance?.destroy) {
    playerInstance.destroy()
    playerInstance = null
  }
  if (videoRef.value) {
    videoRef.value.src = ''
    videoRef.value.load()
  }
}

function playWebRTC(url: string) {
  currentType.value = 'webrtc'
  loading.value = true
  pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })

  pc.ontrack = (event) => {
    if (videoRef.value && event.streams[0]) {
      videoRef.value.srcObject = event.streams[0]
      loading.value = false
      emit('load')
    }
  }

  pc.oniceconnectionstatechange = () => {
    if (pc?.iceConnectionState === 'failed' || pc?.iceConnectionState === 'disconnected') {
      error.value = 'WebRTC连接失败，尝试降级'
      emit('error', 'WebRTC failed')
    }
  }

  const offerUrl = url.replace('webrtc://', 'http://').replace('/rtc/', '/index/api/webrtc?app=live&stream=')
  fetch(offerUrl, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.code === 0) {
        pc!.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: data.sdp }))
        pc!.createAnswer().then(answer => pc!.setLocalDescription(answer))
      }
    })
    .catch(() => {
      error.value = 'WebRTC信令失败'
      emit('error', 'WebRTC signaling failed')
    })
}

async function playFLV(url: string) {
  currentType.value = 'flv'
  loading.value = true
  try {
    const mpegts = await import('mpegts.js')
    if (mpegts.default.isSupported()) {
      playerInstance = mpegts.default.createPlayer({
        type: 'flv',
        url,
        isLive: true,
      })
      playerInstance.attachMediaElement(videoRef.value!)
      playerInstance.load()
      playerInstance.play()
      loading.value = false
      emit('load')
    } else {
      playHLS(url.replace('.flv', '.hls.m3u8'))
    }
  } catch {
    playHLS(url.replace('.flv', '.hls.m3u8'))
  }
}

async function playHLS(url: string) {
  currentType.value = 'hls'
  loading.value = true
  try {
    const Hls = await import('hls.js')
    if (Hls.default.isSupported()) {
      playerInstance = new Hls.default()
      playerInstance.loadSource(url)
      playerInstance.attachMedia(videoRef.value!)
      playerInstance.on(Hls.default.Events.MANIFEST_PARSED, () => {
        loading.value = false
        emit('load')
      })
    } else if (videoRef.value?.canPlayType('application/vnd.apple.mpegurl')) {
      videoRef.value.src = url
      loading.value = false
      emit('load')
    }
  } catch {
    error.value = '不支持的播放格式'
    emit('error', 'unsupported')
  }
}

function play(url: string, forceType?: string) {
  destroyPlayer()
  error.value = ''
  loading.value = true

  if (forceType === 'webrtc' || (!forceType && url.startsWith('webrtc://'))) {
    playWebRTC(url)
  } else if (forceType === 'flv' || (!forceType && url.endsWith('.flv'))) {
    playFLV(url)
  } else if (forceType === 'hls' || (!forceType && url.endsWith('.m3u8'))) {
    playHLS(url)
  } else {
    playFLV(url)
  }
}

watch(() => props.streamUrl, (val) => {
  if (val) play(val)
})

onMounted(() => {
  if (props.streamUrl) play(props.streamUrl)
})

onBeforeUnmount(() => {
  destroyPlayer()
})

defineExpose({ play, destroyPlayer })
</script>

<template>
  <div ref="playerRef" class="live-player" :class="{ 'is-loading': loading }">
    <video ref="videoRef" muted :poster="poster" autoplay playsinline class="player-video" />
    <div v-if="loading" class="player-overlay">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <span class="ml-2">连接中...</span>
    </div>
    <div v-if="error" class="player-overlay error">
      <el-icon :size="24"><WarningFilled /></el-icon>
      <span class="ml-2">{{ error }}</span>
    </div>
    <div class="player-protocol">{{ currentType }}</div>
  </div>
</template>

<style scoped>
.live-player { position: relative; width: 100%; height: 100%; background: #000; overflow: hidden; }
.player-video { width: 100%; height: 100%; object-fit: contain; }
.player-overlay {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.6); color: #fff; font-size: 14px; z-index: 2;
}
.player-overlay.error { color: #f56c6c; }
.player-protocol {
  position: absolute; top: 4px; right: 4px; padding: 1px 6px; border-radius: 2px;
  background: rgba(0,0,0,.5); color: #fff; font-size: 11px; text-transform: uppercase; z-index: 3;
}
.is-loading { cursor: wait; }
</style>
