import { ref } from "vue";
import { Auth } from "@/utils/auth";

export interface OnlineUser {
  id: number;
  name: string;
}

/**
 * 标注实时协作 WebSocket composable：
 * 负责连接（带 token）、在线列表、图片焦点、远端标注事件与锁冲突通知。
 */
export function useCollab() {
  const connected = ref(false);
  const onlineUsers = ref<OnlineUser[]>([]);
  const lastFocus = ref<{ user: OnlineUser; image_id: number } | null>(null);
  const remoteAnnotationTick = ref(0);
  const lockDeniedTick = ref(0);

  let ws: WebSocket | null = null;
  let taskId = 0;
  let closedByUs = false;
  let retry = 0;

  function wsBase(): string {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const origin = window.location.origin.replace(/^http/, "ws");
    return `${origin}${base}`;
  }

  function connect(id: number) {
    taskId = id;
    closedByUs = false;
    const token = Auth.getAccessToken() || "";
    ws = new WebSocket(
      `${wsBase()}/annotation/collab/ws/${taskId}?token=${encodeURIComponent(token)}`
    );
    ws.onopen = () => {
      connected.value = true;
      retry = 0;
    };
    ws.onmessage = (ev) => {
      let msg: any;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "room:presence") {
        onlineUsers.value = msg.users || [];
      } else if (msg.type === "user:join") {
        onlineUsers.value = [
          ...onlineUsers.value.filter((u) => u.id !== msg.user.id),
          msg.user,
        ];
      } else if (msg.type === "user:leave") {
        onlineUsers.value = onlineUsers.value.filter((u) => u.id !== msg.user.id);
      } else if (msg.type === "image:focus") {
        lastFocus.value = { user: msg.user, image_id: msg.image_id };
      } else if (msg.type === "image:lock:denied") {
        lockDeniedTick.value++;
      } else if (typeof msg.type === "string" && msg.type.startsWith("annotate:")) {
        remoteAnnotationTick.value++;
      }
    };
    ws.onclose = () => {
      connected.value = false;
      if (!closedByUs && retry < 5) {
        retry++;
        setTimeout(() => connect(taskId), Math.min(1000 * 2 ** retry, 15000));
      }
    };
    ws.onerror = () => {
      /* 交由 onclose 处理重连 */
    };
  }

  function send(payload: Record<string, any>) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }

  function focus(imageId: number) {
    send({ type: "image:focus", image_id: imageId });
  }

  function cursor(imageId: number, x: number, y: number) {
    send({ type: "cursor:move", image_id: imageId, x, y });
  }

  function close() {
    closedByUs = true;
    ws?.close();
    ws = null;
    connected.value = false;
  }

  return {
    connected,
    onlineUsers,
    lastFocus,
    remoteAnnotationTick,
    lockDeniedTick,
    connect,
    focus,
    cursor,
    close,
  };
}
