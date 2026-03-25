from .base import EDCManagementClient, MetricsRecorder, ScenarioBase
from .negotiation_baseline import NegotiationBaselineScenario
from .transfer_baseline import TransferBaselineScenario
from .policy_overhead import PolicyOverheadScenario

SCENARIO_REGISTRY = {
    "negotiation_baseline": NegotiationBaselineScenario,
    "transfer_baseline": TransferBaselineScenario,
    "policy_overhead": PolicyOverheadScenario,
}
