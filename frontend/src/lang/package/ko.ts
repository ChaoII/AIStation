import common from "./ko/common";
import route from "./ko/route";
import login from "./ko/login";
import navbar from "./ko/navbar";
import lock from "./ko/lock";
import sizeSelect from "./ko/sizeSelect";
import langSelect from "./ko/langSelect";
import settings from "./ko/settings";
import error from "./ko/error";
import system from "./ko/system";
import aiChat from "./ko/ai_chat";
import aiLogs from "./ko/ai_logs";
import aiMarket from "./ko/ai_market";
import aiModel from "./ko/ai_model";
import aiOntology from "./ko/ai_ontology";
import aiWorkflow from "./ko/ai_workflow";
import aiWorkflowEvalAdd from "./ko/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./ko/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./ko/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./ko/ai_workflow_workflow_add";
import annotation from "./ko/annotation";
import application from "./ko/application";
import example from "./ko/example";
import generator from "./ko/generator";
import monitor from "./ko/monitor";
import synthesis from "./ko/synthesis";
import task from "./ko/task";
import train from "./ko/train";
import video from "./ko/video";

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
