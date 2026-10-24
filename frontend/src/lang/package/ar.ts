import common from "./ar/common";
import route from "./ar/route";
import login from "./ar/login";
import navbar from "./ar/navbar";
import lock from "./ar/lock";
import sizeSelect from "./ar/sizeSelect";
import langSelect from "./ar/langSelect";
import settings from "./ar/settings";
import error from "./ar/error";
import system from "./ar/system";
import aiChat from "./ar/ai_chat";
import aiLogs from "./ar/ai_logs";
import aiMarket from "./ar/ai_market";
import aiModel from "./ar/ai_model";
import aiOntology from "./ar/ai_ontology";
import aiWorkflow from "./ar/ai_workflow";
import aiWorkflowEvalAdd from "./ar/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./ar/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./ar/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./ar/ai_workflow_workflow_add";
import annotation from "./ar/annotation";
import application from "./ar/application";
import example from "./ar/example";
import generator from "./ar/generator";
import monitor from "./ar/monitor";
import synthesis from "./ar/synthesis";
import task from "./ar/task";
import train from "./ar/train";
import video from "./ar/video";

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