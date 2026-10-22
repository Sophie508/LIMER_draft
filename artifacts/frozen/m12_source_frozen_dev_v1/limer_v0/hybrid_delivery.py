"""Hybrid observation model; the decision rule is the unchanged M8 rule."""
from limer_v0.batch_loss import BatchLossDetector


class HybridDeliveryDetector(BatchLossDetector):
    RULE_VERSION = "hybrid-delivery-v1"
