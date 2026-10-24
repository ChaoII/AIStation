import common from "./zh-cn/common";
import route from "./zh-cn/route";
import login from "./zh-cn/login";
import navbar from "./zh-cn/navbar";
import lock from "./zh-cn/lock";
import sizeSelect from "./zh-cn/sizeSelect";
import langSelect from "./zh-cn/langSelect";
import settings from "./zh-cn/settings";
import error from "./zh-cn/error";
import system from "./zh-cn/system";
import aiChat from "./zh-cn/ai_chat";
import aiLogs from "./zh-cn/ai_logs";
import aiMarket from "./zh-cn/ai_market";
import aiModel from "./zh-cn/ai_model";
import aiOntology from "./zh-cn/ai_ontology";
import aiWorkflow from "./zh-cn/ai_workflow";
import aiWorkflowEvalAdd from "./zh-cn/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./zh-cn/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./zh-cn/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./zh-cn/ai_workflow_workflow_add";
import annotation from "./zh-cn/annotation";
import application from "./zh-cn/application";
import dashboard from "./zh-cn/dashboard";
import example from "./zh-cn/example";
import generator from "./zh-cn/generator";
import monitor from "./zh-cn/monitor";
import synthesis from "./zh-cn/synthesis";
import task from "./zh-cn/task";
import train from "./zh-cn/train";
import video from "./zh-cn/video";

export default {
  common,
  route,
  login,
  navbar,
  lock,
  sizeSelect,
  langSelect,
  settings,
  error,
  system,
  ai_chat: aiChat,
  ai_logs: aiLogs,
  ai_market: aiMarket,
  ai_model: aiModel,
  ai_ontology: aiOntology,
  ai_workflow: {
    ...aiWorkflow,
    ...aiWorkflowEvalAdd,
    ...aiWorkflowDevelopAdd,
    ...aiWorkflowIntegrationAdd,
    ...aiWorkflowWorkflowAdd,
  },
  annotation,
  application,
  dashboard,
  example,
  generator,
  monitor,
  synthesis,
  task,
  train,
  video,
};
