import type { InjectionKey, Ref } from "vue";
import type { FormInstance } from "element-plus";

/** 代码生成抽屉内 el-form 与父页 ref 同步（校验/重置） */
export const GENCODE_BASIC_FORM_KEY: InjectionKey<Ref<FormInstance | undefined>> =
  Symbol("gencodeBasicForm");
