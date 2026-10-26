import common from "./vi/common";
import route from "./vi/route";
import login from "./vi/login";
import navbar from "./vi/navbar";
import lock from "./vi/lock";
import sizeSelect from "./vi/sizeSelect";
import langSelect from "./vi/langSelect";
import settings from "./vi/settings";
import error from "./vi/error";
import system from "./vi/system";
import aiChat from "./vi/ai_chat";
import aiLogs from "./vi/ai_logs";
import aiMarket from "./vi/ai_market";
import aiModel from "./vi/ai_model";
import aiOntology from "./vi/ai_ontology";
import aiWorkflow from "./vi/ai_workflow";
import aiWorkflowEvalAdd from "./vi/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./vi/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./vi/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./vi/ai_workflow_workflow_add";
import annotation from "./vi/annotation";
import application from "./vi/application";
import dashboard from "./vi/dashboard";
import example from "./vi/example";
import generator from "./vi/generator";
import monitor from "./vi/monitor";
import synthesis from "./vi/synthesis";
import task from "./vi/task";
import train from "./vi/train";
import video from "./vi/video";

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
  ai_workflow: { ...aiWorkflow, ...aiWorkflowEvalAdd, ...aiWorkflowDevelopAdd, ...aiWorkflowIntegrationAdd, ...aiWorkflowWorkflowAdd },
};