import pytest

from crew.assistant import IntentParseError, parse_transfer_intent, propose_intent


class TestParsing:
    def test_basic_move_with_dollar_sign(self):
        intent = parse_transfer_intent("move $50 from checking to rent")
        assert intent == {"kind": "transfer", "from": "checking", "to": "rent", "amount": 50.0, "memo": ""}

    def test_transfer_verb_and_decimal(self):
        intent = parse_transfer_intent("transfer 25.50 from savings to vacation")
        assert intent["amount"] == 25.5
        assert intent["from"] == "savings"

    def test_dollars_word_allowed(self):
        intent = parse_transfer_intent("move 50 dollars from checking to groceries")
        assert intent["amount"] == 50.0

    def test_memo_after_for(self):
        intent = parse_transfer_intent("move $80 from checking to rent for october")
        assert intent["memo"] == "october"

    def test_quoted_names_with_spaces(self):
        intent = parse_transfer_intent('move $20 from "emergency fund" to car repairs')
        assert intent["from"] == "emergency fund"
        assert intent["to"] == "car repairs"

    def test_case_insensitive(self):
        intent = parse_transfer_intent("MOVE $5 From Checking To Rent")
        assert intent["amount"] == 5.0
        assert intent["to"] == "Rent"

    @pytest.mark.parametrize("text", [
        "what's my balance",
        "move to rent",
        "move $50 to rent",
        "move $ fifty from checking to rent",
        "move -10 from checking to rent",
        "",
    ])
    def test_unparseable_input_raises_helpfully(self, text):
        with pytest.raises(IntentParseError) as exc:
            parse_transfer_intent(text)
        assert str(exc.value)


class TestProposing:
    def test_posts_intent_to_local_endpoint(self, monkeypatch):
        sent = {}

        def fake_post(url, json=None, timeout=None):
            sent.update(url=url, payload=json)

            class R:
                status_code = 200

                def json(self):
                    return {"id": "abc", "state": "proposed", "summary": "Move $50.00 from Checking → Rent"}

            return R()

        monkeypatch.setattr("crew.assistant.requests.post", fake_post)
        result = propose_intent(
            "move $50 from checking to rent for october",
            base_url="http://127.0.0.1:8080",
        )
        assert sent["url"] == "http://127.0.0.1:8080/api/actions/propose/local"
        assert sent["payload"]["kind"] == "transfer"
        assert sent["payload"]["to"] == "rent"
        assert result["state"] == "proposed"

    def test_server_error_surfaces_message(self, monkeypatch):
        def fake_post(url, json=None, timeout=None):
            class R:
                status_code = 400

                def json(self):
                    return {"error": "Could not resolve destination 'nowhere'"}

            return R()

        monkeypatch.setattr("crew.assistant.requests.post", fake_post)
        with pytest.raises(IntentParseError) as exc:
            propose_intent("move $5 from checking to nowhere")
        assert "nowhere" in str(exc.value)
