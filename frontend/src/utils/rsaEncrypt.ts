import request from "@/utils/request";

/** 登录密码 RSA 加密工具。

 * 登录前从后端获取 RSA 公钥（RSA-OAEP/SHA-256），用 WebCrypto 对密码加密后再提交，
 * 请求体不再出现明文密码；后端用私钥解密后用现有 bcrypt 校验（向后兼容）。
 * 每次登录都重新拉取公钥，避免后端重启换钥后使用过期公钥导致解密失败。
 */

const PUBLIC_KEY_URL = "/system/auth/rsa-public-key";

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export async function getLoginPublicKey(): Promise<string> {
  const res = await request<ApiResponse<{ public_key: string }>>({
    url: PUBLIC_KEY_URL,
    method: "get",
  });
  const key = res.data?.data?.public_key;
  if (!key) {
    throw new Error("无法获取登录加密公钥");
  }
  return key;
}

/** 用服务端公钥（RSA-OAEP/SHA-256）加密密码，返回 base64 密文。 */
export async function rsaEncryptPassword(password: string): Promise<string> {
  const publicKeyB64 = await getLoginPublicKey();
  const key = await crypto.subtle.importKey(
    "spki",
    base64ToArrayBuffer(publicKeyB64),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"]
  );
  const cipher = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    key,
    new TextEncoder().encode(password)
  );
  return arrayBufferToBase64(cipher);
}
