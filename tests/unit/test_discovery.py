from app.domain.discovery import CustomerProfile, DiscoveryPolicy, SessionState
from app.domain.models import AgentReply, ConversationStage

Stage = ConversationStage
POLICY = DiscoveryPolicy(max_questions=3)


def asking(
    message: str = "Who is it for?", stage: Stage | None = Stage.DISCOVER, **updates: str
) -> AgentReply:
    return AgentReply(message, [], stage, updates)


def showing(stage: Stage | None = Stage.RECOMMEND) -> AgentReply:
    return AgentReply("Here you go", ["black-clutch"], stage)


class TestCustomerProfile:
    def test_apply_returns_a_new_profile_and_leaves_the_old_one_unchanged(self) -> None:
        original = CustomerProfile()
        updated = original.apply({"occasion": "wedding", "colour": "black"})

        assert updated.occasion == "wedding"
        assert updated.colour == "black"
        assert original.occasion == ""

    def test_blank_and_unknown_updates_are_ignored(self) -> None:
        profile = CustomerProfile(colour="black").apply(
            {"colour": "  ", "shoe_size": "40", "style": " classic "}
        )

        assert profile.colour == "black"  # a blank update never erases what we know
        assert profile.style == "classic"
        assert profile.known() == {"colour": "black", "style": "classic"}

    def test_summary_lists_only_known_slots(self) -> None:
        assert CustomerProfile(occasion="birthday", budget="30000").summary() == (
            "occasion: birthday; budget: 30000"
        )
        assert CustomerProfile().summary() == ""


class TestDiscoveryPolicy:
    def test_each_question_without_products_is_counted(self) -> None:
        state = POLICY.update(SessionState(), asking())
        state = POLICY.update(state, asking("And the occasion؟"))

        assert state.questions_asked == 2

    def test_a_reply_without_a_question_is_not_counted(self) -> None:
        assert POLICY.update(SessionState(), asking("Lovely, noted 🤍")).questions_asked == 0

    def test_guidance_appears_only_once_the_limit_is_reached(self) -> None:
        assert POLICY.guidance(SessionState(questions_asked=2)) == ""
        assert "Do NOT ask another one" in POLICY.guidance(SessionState(questions_asked=3))

    def test_showing_products_resets_the_question_counter(self) -> None:
        state = POLICY.update(SessionState(questions_asked=3), showing())

        assert state.questions_asked == 0
        assert POLICY.guidance(state) == ""

    def test_profile_updates_accumulate_across_turns(self) -> None:
        state = POLICY.update(SessionState(), asking(occasion="wedding"))
        state = POLICY.update(state, asking(colour="gold"))

        assert state.profile.known() == {"occasion": "wedding", "colour": "gold"}

    def test_showing_products_moves_to_recommend_then_refine(self) -> None:
        first = POLICY.update(SessionState(stage=Stage.DISCOVER), showing(stage=None))
        second = POLICY.update(first, showing(stage=None))

        assert first.stage == Stage.RECOMMEND
        assert second.stage == Stage.REFINE

    def test_allowed_stage_transition_is_accepted(self) -> None:
        assert POLICY.update(SessionState(stage=Stage.GREET), asking()).stage == Stage.DISCOVER

    def test_claiming_recommend_without_showing_products_is_rejected(self) -> None:
        state = POLICY.update(SessionState(stage=Stage.DISCOVER), asking(stage=Stage.RECOMMEND))

        assert state.stage == Stage.DISCOVER

    def test_missing_or_disallowed_stage_keeps_the_current_one(self) -> None:
        assert POLICY.update(SessionState(stage=Stage.DISCOVER), asking(stage=None)).stage == Stage.DISCOVER
        assert POLICY.update(SessionState(stage=Stage.DISCOVER), asking(stage=Stage.REFINE)).stage == (
            Stage.DISCOVER
        )
