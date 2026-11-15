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

    def test_the_stop_rule_appears_only_once_the_limit_is_reached(self) -> None:
        assert "Do NOT ask another one" not in POLICY.guidance(SessionState(questions_asked=2))
        assert "Do NOT ask another one" in POLICY.guidance(SessionState(questions_asked=3))

    def test_showing_products_resets_the_question_counter(self) -> None:
        state = POLICY.update(SessionState(questions_asked=3), showing())

        assert state.questions_asked == 0
        assert POLICY.guidance(state) == ""  # recommending now: no checklist, no stop rule

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


class TestDiscoveryChecklist:
    def test_lists_every_unknown_topic_in_order_with_the_questions_left(self) -> None:
        note = POLICY.guidance(SessionState(stage=Stage.DISCOVER, questions_asked=1))
        checklist = note.split("BEFORE the latest message:", 1)[1]

        topics = ["who it is for", "the occasion", "the type of piece", "colour or style", "the budget"]
        positions = [checklist.index(topic) for topic in topics]
        assert positions == sorted(positions)
        assert "2 question(s) left" in note

    def test_known_topics_are_left_out_and_style_counts_as_colour_or_style(self) -> None:
        profile = CustomerProfile(for_whom="mother", occasion="birthday", style="classic")
        note = POLICY.guidance(SessionState(stage=Stage.DISCOVER, profile=profile))

        checklist = note.split("BEFORE the latest message:", 1)[1]
        assert "who it is for" not in checklist and "the occasion" not in checklist
        assert "colour or style" not in checklist
        assert "the type of piece" in checklist and "the budget" in checklist

    def test_a_complete_checklist_says_recommend_now(self) -> None:
        profile = CustomerProfile(
            for_whom="herself", occasion="wedding", category="clutch", colour="gold", budget="50000"
        )
        note = POLICY.guidance(SessionState(stage=Stage.DISCOVER, profile=profile))

        assert "complete" in note and "recommend" in note


class TestShownProducts:
    def test_shown_products_are_remembered_in_order_without_duplicates(self) -> None:
        state = POLICY.update(SessionState(), AgentReply("a", ["a", "b"], Stage.RECOMMEND))
        state = POLICY.update(state, AgentReply("b", ["c", "a"], Stage.REFINE))

        assert state.shown_products == ("b", "c", "a")

    def test_only_the_most_recent_products_are_kept(self) -> None:
        policy = DiscoveryPolicy(max_questions=3, shown_limit=2)

        state = policy.update(SessionState(), AgentReply("x", ["a", "b", "c"], Stage.RECOMMEND))

        assert state.shown_products == ("b", "c")

    def test_cards_already_seen_are_not_sent_again(self) -> None:
        state = SessionState(shown_products=("a", "b"))

        assert POLICY.cards_to_send(state, ["a", "c"]) == ["c"]

    def test_a_reply_with_only_seen_products_still_sends_them(self) -> None:
        state = SessionState(shown_products=("a", "b"))

        assert POLICY.cards_to_send(state, ["b"]) == ["b"]  # the customer asked for it again


class TestDodgedQuestions:
    def test_two_answers_without_any_new_detail_stop_the_questions(self) -> None:
        policy = DiscoveryPolicy(max_questions=5)  # far from the question limit
        state = policy.update(SessionState(), asking("Is it for you or a gift?"))
        state = policy.update(state, asking("Everyday or an occasion?"))  # "I don't know": nothing learned
        assert "Do NOT ask anything more" not in policy.guidance(state)

        state = policy.update(state, asking("What colours do you like?"))  # "anything": nothing learned

        assert state.dodged_questions == 2
        assert "Do NOT ask anything more" in policy.guidance(state)

    def test_an_answer_with_a_new_detail_resets_the_count(self) -> None:
        state = POLICY.update(SessionState(), asking("Is it for you or a gift?"))
        state = POLICY.update(state, asking("Everyday or an occasion?"))
        state = POLICY.update(state, asking("What colours?", occasion="wedding"))

        assert state.dodged_questions == 0

    def test_repeating_an_already_known_detail_is_not_new(self) -> None:
        state = SessionState(profile=CustomerProfile(occasion="wedding"), awaiting_answer=True)

        assert POLICY.update(state, asking("And the colour?", occasion="wedding")).dodged_questions == 1

    def test_showing_products_resets_the_count(self) -> None:
        state = SessionState(awaiting_answer=True, dodged_questions=2)

        assert POLICY.update(state, showing()).dodged_questions == 0
