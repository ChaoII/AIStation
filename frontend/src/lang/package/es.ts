import common from "./es/common";
import route from "./es/route";
import login from "./es/login";
import navbar from "./es/navbar";
import lock from "./es/lock";
import sizeSelect from "./es/sizeSelect";
import langSelect from "./es/langSelect";
import settings from "./es/settings";
import error from "./es/error";
import system from "./es/system";
import aiChat from "./es/ai_chat";
import aiLogs from "./es/ai_logs";
import aiMarket from "./es/ai_market";
import aiModel from "./es/ai_model";
import aiOntology from "./es/ai_ontology";
import aiWorkflow from "./es/ai_workflow";
import aiWorkflowEvalAdd from "./es/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./es/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./es/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./es/ai_workflow_workflow_add";
import annotation from "./es/annotation";
import application from "./es/application";
import example from "./es/example";
import generator from "./es/generator";
import monitor from "./es/monitor";
import synthesis from "./es/synthesis";
import task from "./es/task";
import train from "./es/train";
import video from "./es/video";

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
  example,
  generator,
  monitor,
  synthesis,
  task,
  train,
  video,
  ai_workflow: { ...aiWorkflow, ...aiWorkflowEvalAdd, ...aiWorkflowDevelopAdd, ...aiWorkflowIntegrationAdd, ...aiWorkflowWorkflowAdd },
};