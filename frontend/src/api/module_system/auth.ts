import request from "@/utils/request";
import { rsaEncryptPassword } from "@/utils/rsaEncrypt";

const API_PATH = "/system/auth";

const AuthAPI = {
  async login(body: LoginFormData) {
    // 登录前用服务端 RSA 公钥加密密码，避免请求体明文传输密码
    const encryptedPassword = await rsaEncryptPassword(body.password);
    return request<ApiResponse<LoginResult>>({
      url: `${API_PATH}/login`,
      method: "post",
      headers: {
        "Content-Type": "multipart/form-data",
      },
      data: { ...body, password: encryptedPassword },
    });
  },

  refreshToken(body: RefreshToekenBody) {
    return request<ApiResponse<LoginResult>>({
      url: `${API_PATH}/token/refresh`,
      method: "post",
      data: body,
    });
  },

  getCaptcha() {
    return request<ApiResponse<CaptchaInfo>>({
      url: `${API_PATH}/captcha/get`,
      method: "get",
    });
  },

  logout(body: LogoutBody) {
    return request<ApiResponse>({
      url: `${API_PATH}/logout`,
      method: "post",
      data: body,
    });
  },
};

export default AuthAPI;

/** 登录表单数据 */
export interface LoginFormData {
  username: string;
  password: string;
  captcha_key: string;
  captcha: string;
  remember: boolean;
  login_type: string;
}

// 刷新令牌
export interface RefreshToekenBody {
  refresh_token: string;
}

/** 登录响应 */
export interface LoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** 验证码信息 */
export interface CaptchaInfo {
  enable: boolean;
  key: string;
  img_base: string;
}

/** 退出登录操作 */
export interface LogoutBody {
  token: string;
}
