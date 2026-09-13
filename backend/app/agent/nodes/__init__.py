"""主图节点包（BE-036，设计 §11~§20）。

命名规则（设计 §2.1）：带 LLM 的节点以 _agent 结尾，
确定性节点以 _node 结尾。
"""

from app.agent.nodes.action_router_node import ACTION_TARGETS, ActionRouterNode, route_action
from app.agent.nodes.answer_generator_agent import AnswerGeneratorAgent
from app.agent.nodes.direct_answer_agent import DirectAnswerAgent
from app.agent.nodes.fallback_generator_agent import FallbackGeneratorAgent
from app.agent.nodes.final_answer_node import FinalAnswerNode
from app.agent.nodes.grounding_checker_agent import GroundingCheckerAgent
from app.agent.nodes.observation_node import ObservationNode
from app.agent.nodes.orchestrator_agent import OrchestratorAgent
from app.agent.nodes.query_router_agent import QueryRouterAgent

__all__ = [
    "ACTION_TARGETS",
    "ActionRouterNode",
    "AnswerGeneratorAgent",
    "DirectAnswerAgent",
    "FallbackGeneratorAgent",
    "FinalAnswerNode",
    "GroundingCheckerAgent",
    "ObservationNode",
    "OrchestratorAgent",
    "QueryRouterAgent",
    "route_action",
]
