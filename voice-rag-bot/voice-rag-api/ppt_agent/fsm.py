from loguru import logger
from .session import PresentationSession, State

TRANSITIONS: dict[tuple[State, str], State] = {
    # Normal presentation flow
    (State.IDLE,       "INIT"):           State.PRESENTING,
    (State.PRESENTING, "NEXT_SENTENCE"):  State.PRESENTING,
    (State.PRESENTING, "END"):            State.QA_OPEN,

    # Interrupt from any speaking/idle state
    (State.PRESENTING, "INTERRUPT"):      State.LISTENING,
    (State.IDLE,       "INTERRUPT"):      State.LISTENING,
    (State.QA_OPEN,    "INTERRUPT"):      State.LISTENING,
    (State.THINKING,   "INTERRUPT"):      State.LISTENING,
    (State.RESPONDING, "INTERRUPT"):      State.LISTENING,

    # Q&A cycle
    (State.LISTENING,  "SILENCE"):        State.THINKING,
    (State.THINKING,   "RESPONSE_READY"): State.RESPONDING,

    # Resume after answering
    (State.RESPONDING, "NEXT_SENTENCE"):  State.PRESENTING,
    (State.RESPONDING, "END"):            State.QA_OPEN,

    # Q&A window timeout → done
    (State.QA_OPEN,    "END"):            State.IDLE,

    # Safety valves
    (State.IDLE,       "NEXT_SENTENCE"):  State.IDLE,
}

class FSM:
    def __init__(self, session: PresentationSession):
        self.s = session

    @property
    def current_state(self) -> State:
        return self.s.state

    def handle(self, event: str) -> State:
        key = (self.s.state, event)
        if key not in TRANSITIONS:
            logger.warning(f"[FSM] Invalid event '{event}' in state {self.s.state.value} — ignored")
            return self.s.state

        old = self.s.state
        self.s.state = TRANSITIONS[key]
        logger.info(f"[FSM] {old.value} + {event} → {self.s.state.value}")

        # Side effects
        if event == "INTERRUPT":
            self.s.resume_sentence_index = self.s.sentence_index
            self.s.interrupt_count += 1
            self.s.tts_kill.set()          # kill TTS immediately

        if event == "NEXT_SENTENCE" and old == State.RESPONDING:
            self.s.sentence_index = self.s.resume_sentence_index

        if event == "NEXT_SENTENCE" and old == State.PRESENTING:
            self.s.sentence_index += 1

        if event in ("END", "INIT"):
            self.s.tts_kill.clear()

        return self.s.state
