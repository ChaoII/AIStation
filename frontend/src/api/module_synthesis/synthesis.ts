import request from "@/utils/request";

const API_PATH = "/synthesis";

export interface GeneratedPlateItem {
  filename: string;
  text: string;
  label: string;
  plate_type: string;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  char_boxes: { x1: number; y1: number; x2: number; y2: number }[];
  width: number;
  height: number;
  object_key?: string;
  image_id?: number;
  preview_base64?: string;
}

export interface PlateTypeOption {
  key: string;
  label: string;
}

export interface ProviderInfo {
  key: string;
  label: string;
  description: string;
  task_type: string;
  classes: string[];
  plate_types: PlateTypeOption[];
}

export interface SynthesisJob {
  id: number;
  provider: string;
  name: string;
  dataset_id: number | null;
  params: any;
  status: string;
  total: number;
  done: number;
  error: string | null;
  results: any[];
  created_time: string | null;
}

export const SynthesisAPI = {
  getProviders() {
    return request<ApiResponse<ProviderInfo[]>>({
      url: `${API_PATH}/providers`,
      method: "get",
    });
  },
  getJobs(params?: { page_no?: number; page_size?: number }) {
    return request<ApiResponse<{ total: number; items: SynthesisJob[] }>>({
      url: `${API_PATH}/jobs`,
      method: "get",
      params: { page_no: 1, page_size: 20, ...params },
    });
  },
  generatePlate(data: {
    dataset_id?: number;
    count: number;
    seed?: number;
    plate_type?: string;
    disturbances?: Record<string, boolean>;
    upload?: boolean;
    with_annotation?: boolean;
    width?: number;
    height?: number;
  }) {
    return request<ApiResponse<{ provider: string; job_id: number | null; uploaded: boolean; items: GeneratedPlateItem[] }>>({
      url: `${API_PATH}/license-plate/generate`,
      method: "post",
      data,
      timeout: 0,
    });
  },
};
