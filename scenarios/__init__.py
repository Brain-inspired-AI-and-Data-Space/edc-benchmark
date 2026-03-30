from .base import EDCManagementClient, MetricsRecorder, ScenarioBase
from .negotiation_baseline import NegotiationBaselineScenario
from .transfer_baseline import TransferBaselineScenario
from .policy_overhead import PolicyOverheadScenario
from .provider_restart_during_transfer import ProviderRestartDuringTransferScenario
from .network_delay_transfer import NetworkDelayTransferScenario
from .transfer_interruption import TransferInterruptionScenario
from .consumer_restart_during_transfer import ConsumerRestartDuringTransferScenario
from .packet_loss_transfer import PacketLossTransferScenario
from .concurrent_transfer import TransferConcurrentScenario

SCENARIO_REGISTRY = {
    "negotiation_baseline": NegotiationBaselineScenario,
    "transfer_baseline": TransferBaselineScenario,
    "policy_overhead": PolicyOverheadScenario,
    "provider_restart_during_transfer": ProviderRestartDuringTransferScenario,
    "consumer_restart_during_transfer": ConsumerRestartDuringTransferScenario,

    "network_delay_transfer": NetworkDelayTransferScenario,
    "transfer_interruption": TransferInterruptionScenario,
    "packet_loss_transfer": PacketLossTransferScenario,
    "concurrent_transfer":TransferConcurrentScenario,

}
