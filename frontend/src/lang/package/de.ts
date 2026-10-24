import common from "./de/common";
import route from "./de/route";
import login from "./de/login";
import navbar from "./de/navbar";
import lock from "./de/lock";
import sizeSelect from "./de/sizeSelect";
import langSelect from "./de/langSelect";
import settings from "./de/settings";
import error from "./de/error";
import system from "./de/system";
import aiChat from "./de/ai_chat";
import aiLogs from "./de/ai_logs";
import aiMarket from "./de/ai_market";
import aiModel from "./de/ai_model";
import aiOntology from "./de/ai_ontology";
import aiWorkflow from "./de/ai_workflow";
import aiWorkflowEvalAdd from "./de/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./de/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./de/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./de/ai_workflow_workflow_add";
import annotation from "./de/annotation";
import application from "./de/application";
import example from "./de/example";
import generator from "./de/generator";
import monitor from "./de/monitor";
import synthesis from "./de/synthesis";
import task from "./de/task";
import train from "./de/train";
import video from "./de/video";

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