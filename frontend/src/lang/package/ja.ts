import common from "./ja/common";
import route from "./ja/route";
import login from "./ja/login";
import navbar from "./ja/navbar";
import lock from "./ja/lock";
import sizeSelect from "./ja/sizeSelect";
import langSelect from "./ja/langSelect";
import settings from "./ja/settings";
import error from "./ja/error";
import system from "./ja/system";
import aiChat from "./ja/ai_chat";
import aiLogs from "./ja/ai_logs";
import aiMarket from "./ja/ai_market";
import aiModel from "./ja/ai_model";
import aiOntology from "./ja/ai_ontology";
import aiWorkflow from "./ja/ai_workflow";
import aiWorkflowEvalAdd from "./ja/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./ja/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./ja/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./ja/ai_workflow_workflow_add";
import annotation from "./ja/annotation";
import application from "./ja/application";
import example from "./ja/example";
import generator from "./ja/generator";
import monitor from "./ja/monitor";
import synthesis from "./ja/synthesis";
import task from "./ja/task";
import train from "./ja/train";
import video from "./ja/video";

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
