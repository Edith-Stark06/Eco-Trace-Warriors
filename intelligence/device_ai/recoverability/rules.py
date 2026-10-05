"""Modular rule engine for recoverability assessment (milestone M1.8).

The engine's *signals* — the device-type profile, the completeness of the
identity fields, the presence of batteries/hazards, and the quality of the
fusion that produced the context — are each the responsibility of one small,
independent :class:`Rule`. Every rule inspects a fused
:class:`~device_ai.fusion.models.DeviceContext` plus its resolved
:class:`~device_ai.recoverability.profiles.DeviceProfile` and emits zero or more
:class:`~device_ai.recoverability.models.RuleOutcome` s — uniform, additive
contributions the scoring engine folds into the final report.

Because the outcomes are additive and the rules are independent, the rule set
is a plain ordered list that can be extended, replaced or reordered without
touching the scoring logic — the scoring engine only ever sums deltas, takes the
most severe hazard floor, multiplies confidence factors and reads forced
actions.

Reference rule order (matters only for stable reasoning/warning output):

1. :class:`BaselineProfileRule`     — seeds the scores and hazard from the profile.
2. :class:`IdentityCompletenessRule`— rewards/penalizes by identity presence.
3. :class:`BatteryHazardRule`       — escalates hazard + penalizes recycling.
4. :class:`HighHazardDisposalRule`  — forces hazardous disposal for HIGH-hazard
   classes (CRT, standalone batteries).
5. :class:`ConflictPenaltyRule`     — damps confidence on fusion conflicts.
6. :class:`LowConfidenceRule`       — forces manual review on low confidence.
7. :class:`UnknownDeviceRule`       — forces manual review for unrecognized types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .config import RecoverabilityConfig
from .models import HazardLevel, RecommendedAction, RuleOutcome
from .profiles import DeviceProfile

if TYPE_CHECKING:  # Type-only import keeps the rule engine free of a hard
    # runtime coupling to the fusion layer (the context is passed in).
    from ..fusion.models import DeviceContext


class Rule(ABC):
    """One independent, composable recoverability signal.

    A rule reads the fused context and the resolved profile, applies its own
    threshold/weight logic (always reading values from the injected
    :class:`RecoverabilityConfig`, never hardcoding them) and reports its effect
    as a list of :class:`RuleOutcome` s. Rules are pure: they mutate nothing and
    depend only on their inputs, so they are deterministic and independently
    testable.
    """

    name: str = "rule"

    @abstractmethod
    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Return the outcomes this rule contributes.

        Args:
            context: The fused device context being assessed.
            profile: The resolved device-type profile for the context.
            config: The engine configuration (thresholds and weights).

        Returns:
            The outcomes this rule contributes (may be empty).
        """


def _is_known_identity(context: DeviceContext) -> bool:
    """Return whether any identifying field (model/serial/imei) is present."""
    return any((context.model, context.serial_number, context.imei))


class BaselineProfileRule(Rule):
    """Seed the three scores and the hazard level from the device profile.

    This rule is the engine's foundation: it turns the static knowledge table
    into the initial report values. Every later rule only adjusts these
    baselines, which is what keeps the profiles and the rules independently
    maintainable.
    """

    name = "baseline_profile"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Seed the report from the profile baseline and intrinsic hazard."""
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    f"Device-type profile for '{profile.device_type}' establishes "
                    f"baseline recoverability: repairability "
                    f"{profile.repairability:.0%}, reusability "
                    f"{profile.reusability:.0%}, recyclability "
                    f"{profile.recyclability:.0%}."
                ),
                repairability_delta=profile.repairability,
                reusability_delta=profile.reusability,
                recyclability_delta=profile.recyclability,
                hazard_floor=profile.hazard,
            )
        ]


class IdentityCompletenessRule(Rule):
    """Adjust the scores by how identifiable the specific unit is.

    A device whose model, serial or IMEI is known is trackable, wipeable and
    has identifiable parts — which raises its fitness for reuse and repair. A
    device with *no* identifying field at all is harder to track and prepare, so
    its reusability is penalized and the operator is warned.
    """

    name = "identity_completeness"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Reward identifiable units; penalize and warn when identity is absent."""
        present = [
            label
            for label, value in (
                ("model", context.model),
                ("serial number", context.serial_number),
                ("IMEI", context.imei),
            )
            if value
        ]
        if present:
            return [
                RuleOutcome(
                    rule=self.name,
                    reason=(
                        "Identity is complete ("
                        + ", ".join(present)
                        + "): the device is trackable, wipeable and its parts "
                        "identifiable, improving repair and reuse prospects."
                    ),
                    reusability_delta=config.identity_reuse_bonus,
                    repairability_delta=config.identity_repair_bonus,
                )
            ]
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    "No identifying field (model, serial number or IMEI) is "
                    "available, so the device cannot be reliably tracked or "
                    "prepared for reuse."
                ),
                reusability_delta=-config.missing_identity_reuse_penalty,
                warning=(
                    "Missing identity: model, serial number and IMEI are all "
                    "unknown. Confirm provenance before reuse."
                ),
            )
        ]


class BatteryHazardRule(Rule):
    """Escalate hazard and penalize recycling when a battery is present.

    Embedded batteries are a well-understood handling concern: they demand
    special transport/storage and must be separated before material recovery.
    When the profile says the class carries a battery, the hazard floor is
    raised to ``MEDIUM`` (when enabled) and recyclability is reduced for the
    separation step.
    """

    name = "battery_hazard"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Escalate the hazard floor and penalize recycling for battery classes."""
        if not profile.has_battery:
            return []
        floor = HazardLevel.MEDIUM if config.battery_hazard_floor_enabled else None
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    "Device class carries a battery: it must be handled and "
                    "transported as hazardous and the battery separated before "
                    "material recovery."
                ),
                hazard_floor=floor,
                recyclability_delta=-config.battery_recyclability_penalty,
            )
        ]


class HighHazardDisposalRule(Rule):
    """Force hazardous disposal for classes with an intrinsic HIGH hazard.

    Some classes are hazardous by construction — a CRT's leaded glass and
    phosphors, a standalone battery cell. For those, the engine short-circuits
    the normal repair/reuse/recycle ladder: the hazard floor is set to ``HIGH``
    and the recommended action is forced to hazardous disposal.
    """

    name = "high_hazard_disposal"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Force hazardous disposal for classes with an intrinsic HIGH hazard."""
        if profile.hazard is not HazardLevel.HIGH:
            return []
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    f"'{profile.device_type}' carries an intrinsic high hazard "
                    "(e.g. leaded glass, phosphors, live cells) and must be "
                    "disposed of through the hazardous waste stream."
                ),
                hazard_floor=HazardLevel.HIGH,
                force_action=RecommendedAction.HAZARDOUS_DISPOSAL,
            )
        ]


class ConflictPenaltyRule(Rule):
    """Damp confidence and warn when the fusion reported conflicts.

    Conflicting module evidence means the device's identity is uncertain; the
    assessment built on it deserves less confidence and an operator-facing
    warning, even though the scores themselves are unchanged.
    """

    name = "conflict_penalty"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Damp confidence and warn when fusion reported cross-module conflicts."""
        if not context.has_conflicts:
            return []
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    "Fusion reported conflicting evidence across modules, so "
                    "the confidence in this assessment is reduced."
                ),
                confidence_factor=config.conflict_confidence_factor,
                warning=(
                    "Conflicting module evidence was fused; verify the device "
                    "identity before acting on this recommendation."
                ),
            )
        ]


class LowConfidenceRule(Rule):
    """Force manual review when the fused confidence is too low.

    When the context's own aggregate confidence falls below the configured
    threshold, the engine refuses to guess: it forces a manual review, damps the
    report confidence and warns the operator.
    """

    name = "low_confidence"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Force a manual review when the fused confidence is too low."""
        if context.confidence >= config.low_confidence_threshold:
            return []
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    f"Fused device confidence ({context.confidence:.2f}) is "
                    f"below the review threshold "
                    f"({config.low_confidence_threshold:.2f}); a human must "
                    "decide this device's disposition."
                ),
                confidence_factor=config.low_confidence_factor,
                force_action=RecommendedAction.MANUAL_REVIEW,
                warning=(
                    "Low fused confidence; manual review required before "
                    "disposition."
                ),
            )
        ]


class UnknownDeviceRule(Rule):
    """Force manual review for device types the engine does not recognize.

    The profile table is deliberately finite; encountering a type outside it is
    a signal the engine should not guess a disposition for. The unknown profile
    is recognized by its ``known=False`` flag, and this rule converts that into a
    manual review with a warning.
    """

    name = "unknown_device"

    def evaluate(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Force a manual review for device types outside the profile table."""
        if profile.known:
            return []
        return [
            RuleOutcome(
                rule=self.name,
                reason=(
                    f"'{profile.device_type}' is not a recognized device type, "
                    "so its disposition cannot be assessed automatically."
                ),
                confidence_factor=config.unknown_device_confidence_factor,
                force_action=RecommendedAction.MANUAL_REVIEW,
                warning=(
                    "Unrecognized device type; disposition requires manual " "review."
                ),
            )
        ]


#: The reference rule set, run in this fixed order by the default engine.
DEFAULT_RULES: tuple[Rule, ...] = (
    BaselineProfileRule(),
    IdentityCompletenessRule(),
    BatteryHazardRule(),
    HighHazardDisposalRule(),
    ConflictPenaltyRule(),
    LowConfidenceRule(),
    UnknownDeviceRule(),
)


class RuleEngine:
    """Run a rule set over a context and collect the outcomes.

    Args:
        rules: The ordered rule set to run. Defaults to :data:`DEFAULT_RULES`; a
            caller may pass any iterable of :class:`Rule` to extend, replace or
            reorder the assessment logic.
    """

    def __init__(self, rules: Iterable[Rule] = DEFAULT_RULES) -> None:
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        """Return the configured rule set, in evaluation order."""
        return self._rules

    def run(
        self,
        context: DeviceContext,
        profile: DeviceProfile,
        config: RecoverabilityConfig,
    ) -> list[RuleOutcome]:
        """Evaluate every rule and concatenate its outcomes.

        Rules are pure and independent, so running them in a fixed order yields
        deterministic, ordered reasoning regardless of the rule set chosen.

        Args:
            context: The fused device context being assessed.
            profile: The resolved device-type profile.
            config: The engine configuration.

        Returns:
            All outcomes, in rule order.
        """
        outcomes: list[RuleOutcome] = []
        for rule in self._rules:
            outcomes.extend(rule.evaluate(context, profile, config))
        return outcomes
