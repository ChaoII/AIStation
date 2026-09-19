export interface WorkbenchApi {
  getTaskDetail(taskId: number): Promise<any>;
  listImages(params: any): Promise<any>;
  getImages(datasetId: number, taskId: number, page: number, pageSize: number, opts?: { silent?: boolean }): Promise<any>;
  getPresignedUrl(imageId: number, taskId: number): Promise<any>;
  loadAnnotations(taskId: number, imageId: number): Promise<any>;
  saveAnnotations(taskId: number, imageId: number, data: any[]): Promise<any>;
  lockImage(imageId: number, taskId: number): Promise<any>;
  unlockImage(imageId: number, taskId: number): Promise<any>;
  updateTask(taskId: number, patch: any): Promise<any>;
  getTaskProgress(taskId: number): Promise<any>;
}

export interface WorkbenchConfig {
  taskType: string;
  classes: { id: number; name: string; color: string; keypoint_names?: string[] }[];
  classificationMode: "single" | "multi";
}
