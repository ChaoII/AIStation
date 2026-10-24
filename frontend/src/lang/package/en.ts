import common from "./en/common";
import route from "./en/route";
import login from "./en/login";
import navbar from "./en/navbar";
import lock from "./en/lock";
import sizeSelect from "./en/sizeSelect";
import langSelect from "./en/langSelect";
import settings from "./en/settings";
import error from "./en/error";
import system from "./en/system";
import aiChat from "./en/ai_chat";
import aiLogs from "./en/ai_logs";
import aiMarket from "./en/ai_market";
import aiModel from "./en/ai_model";
import aiOntology from "./en/ai_ontology";
import aiWorkflow from "./en/ai_workflow";
import aiWorkflowEvalAdd from "./en/ai_workflow_eval_add";
import aiWorkflowDevelopAdd from "./en/ai_workflow_develop_add";
import aiWorkflowIntegrationAdd from "./en/ai_workflow_integration_add";
import aiWorkflowWorkflowAdd from "./en/ai_workflow_workflow_add";
import annotation from "./en/annotation";
import application from "./en/application";
import example from "./en/example";
import generator from "./en/generator";
import monitor from "./en/monitor";
import synthesis from "./en/synthesis";
import task from "./en/task";
import train from "./en/train";
import video from "./en/video";

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
  ai_workflow: {
    ...aiWorkflow,
    ...aiWorkflowEvalAdd,
    ...aiWorkflowDevelopAdd,
    ...aiWorkflowIntegrationAdd,
    ...aiWorkflowWorkflowAdd,
  },
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
