import common from "./th/common";
import route from "./th/route";
import login from "./th/login";
import navbar from "./th/navbar";
import lock from "./th/lock";
import sizeSelect from "./th/sizeSelect";
import langSelect from "./th/langSelect";
import settings from "./th/settings";
import error from "./th/error";
import system from "./th/system";
import aiChat from "./th/ai_chat";
import aiLogs from "./th/ai_logs";
import aiMarket from "./th/ai_market";
import aiModel from "./th/ai_model";
import aiOntology from "./th/ai_ontology";
import aiWorkflow from "./th/ai_workflow";
import aiWorkflowEvalAdd from "./th/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./th/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./th/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./th/ai_workflow_workflow_add";
import annotation from "./th/annotation";
import application from "./th/application";
import dashboard from "./th/dashboard";
import example from "./th/example";
import generator from "./th/generator";
import monitor from "./th/monitor";
import synthesis from "./th/synthesis";
import task from "./th/task";
import train from "./th/train";
import video from "./th/video";

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