import common from "./ru/common";
import route from "./ru/route";
import login from "./ru/login";
import navbar from "./ru/navbar";
import lock from "./ru/lock";
import sizeSelect from "./ru/sizeSelect";
import langSelect from "./ru/langSelect";
import settings from "./ru/settings";
import error from "./ru/error";
import system from "./ru/system";
import aiChat from "./ru/ai_chat";
import aiLogs from "./ru/ai_logs";
import aiMarket from "./ru/ai_market";
import aiModel from "./ru/ai_model";
import aiOntology from "./ru/ai_ontology";
import aiWorkflow from "./ru/ai_workflow";
import aiWorkflowEvalAdd from "./ru/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./ru/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./ru/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./ru/ai_workflow_workflow_add";
import annotation from "./ru/annotation";
import application from "./ru/application";
import example from "./ru/example";
import generator from "./ru/generator";
import monitor from "./ru/monitor";
import synthesis from "./ru/synthesis";
import task from "./ru/task";
import train from "./ru/train";
import video from "./ru/video";

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