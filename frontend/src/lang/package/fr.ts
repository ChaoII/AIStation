import common from "./fr/common";
import route from "./fr/route";
import login from "./fr/login";
import navbar from "./fr/navbar";
import lock from "./fr/lock";
import sizeSelect from "./fr/sizeSelect";
import langSelect from "./fr/langSelect";
import settings from "./fr/settings";
import error from "./fr/error";
import system from "./fr/system";
import aiChat from "./fr/ai_chat";
import aiLogs from "./fr/ai_logs";
import aiMarket from "./fr/ai_market";
import aiModel from "./fr/ai_model";
import aiOntology from "./fr/ai_ontology";
import aiWorkflow from "./fr/ai_workflow";
import aiWorkflowEvalAdd from "./fr/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./fr/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./fr/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./fr/ai_workflow_workflow_add";
import annotation from "./fr/annotation";
import application from "./fr/application";
import dashboard from "./fr/dashboard";
import example from "./fr/example";
import generator from "./fr/generator";
import monitor from "./fr/monitor";
import synthesis from "./fr/synthesis";
import task from "./fr/task";
import train from "./fr/train";
import video from "./fr/video";

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