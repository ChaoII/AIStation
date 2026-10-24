import common from "./zh-hant/common";
import route from "./zh-hant/route";
import login from "./zh-hant/login";
import navbar from "./zh-hant/navbar";
import lock from "./zh-hant/lock";
import sizeSelect from "./zh-hant/sizeSelect";
import langSelect from "./zh-hant/langSelect";
import settings from "./zh-hant/settings";
import error from "./zh-hant/error";
import system from "./zh-hant/system";
import aiChat from "./zh-hant/ai_chat";
import aiLogs from "./zh-hant/ai_logs";
import aiMarket from "./zh-hant/ai_market";
import aiModel from "./zh-hant/ai_model";
import aiOntology from "./zh-hant/ai_ontology";
import aiWorkflow from "./zh-hant/ai_workflow";
import aiWorkflowEvalAdd from "./zh-hant/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./zh-hant/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./zh-hant/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./zh-hant/ai_workflow_workflow_add";
import annotation from "./zh-hant/annotation";
import application from "./zh-hant/application";
import example from "./zh-hant/example";
import generator from "./zh-hant/generator";
import monitor from "./zh-hant/monitor";
import synthesis from "./zh-hant/synthesis";
import task from "./zh-hant/task";
import train from "./zh-hant/train";
import video from "./zh-hant/video";

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
  ai_workflow: { ...aiWorkflow, ...aiWorkflowEvalAdd, ...aiWorkflowDevelopAdd, ...aiWorkflowIntegrationAdd, ...aiWorkflowWorkflowAdd },
  annotation,
  application,
  example,
  generator,
  monitor,
  synthesis,
  task,
  train,
  video,
};
