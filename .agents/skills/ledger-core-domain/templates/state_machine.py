"""Production Transaction Finite-State Machine template adhering to GoF State Pattern.

Governs state transitions:
INITIATED -> LOCKED -> COMMITTED -> SETTLED
                          |            |
                          v            v
                        FAILED      REVERSED
"""

from abc import ABC, abstractmethod
from enum import StrEnum


class TransactionState(StrEnum):
    INITIATED = "INITIATED"
    LOCKED = "LOCKED"
    COMMITTED = "COMMITTED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class InvalidStateTransitionError(Exception):
    """Raised when an illegal transition is attempted on the state machine."""
    def __init__(self, from_state: TransactionState, to_state: TransactionState) -> None:
        super().__init__(f"Illegal state transition from {from_state.value} to {to_state.value}.")
        self.from_state = from_state
        self.to_state = to_state


class ITransactionState(ABC):
    """Abstract State interface."""

    @property
    @abstractmethod
    def state_name(self) -> TransactionState:
        pass

    @abstractmethod
    def allowed_transitions(self) -> set[TransactionState]:
        pass

    def can_transition_to(self, target: TransactionState) -> bool:
        return target in self.allowed_transitions()

    def transition_to(self, target: TransactionState) -> "ITransactionState":
        if not self.can_transition_to(target):
            raise InvalidStateTransitionError(self.state_name, target)
        return _STATE_MAP[target]


class InitiatedState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.INITIATED

    def allowed_transitions(self) -> set[TransactionState]:
        return {TransactionState.LOCKED, TransactionState.FAILED}


class LockedState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.LOCKED

    def allowed_transitions(self) -> set[TransactionState]:
        return {TransactionState.COMMITTED, TransactionState.FAILED}


class CommittedState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.COMMITTED

    def allowed_transitions(self) -> set[TransactionState]:
        return {TransactionState.SETTLED, TransactionState.FAILED}


class SettledState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.SETTLED

    def allowed_transitions(self) -> set[TransactionState]:
        return {TransactionState.REVERSED}


class FailedState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.FAILED

    def allowed_transitions(self) -> set[TransactionState]:
        return set()


class ReversedState(ITransactionState):
    @property
    def state_name(self) -> TransactionState:
        return TransactionState.REVERSED

    def allowed_transitions(self) -> set[TransactionState]:
        return set()


_STATE_MAP: dict[TransactionState, ITransactionState] = {
    TransactionState.INITIATED: InitiatedState(),
    TransactionState.LOCKED: LockedState(),
    TransactionState.COMMITTED: CommittedState(),
    TransactionState.SETTLED: SettledState(),
    TransactionState.FAILED: FailedState(),
    TransactionState.REVERSED: ReversedState(),
}


class TransactionStateMachine:
    """Manages transaction lifecycle through deterministic state pattern transitions."""

    def __init__(self, initial_state: TransactionState = TransactionState.INITIATED) -> None:
        self._current_state: ITransactionState = _STATE_MAP[initial_state]

    @property
    def state(self) -> TransactionState:
        return self._current_state.state_name

    def can_transition_to(self, target: TransactionState | str) -> bool:
        resolved = TransactionState(target) if isinstance(target, str) else target
        return self._current_state.can_transition_to(resolved)

    def transition_to(self, target: TransactionState | str) -> None:
        resolved = TransactionState(target) if isinstance(target, str) else target
        self._current_state = self._current_state.transition_to(resolved)
