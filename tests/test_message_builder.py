from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.services.message_builder import build_high_intent_message


def test_message_uses_present_context_without_internal_metadata() -> None:
    request = HighIntentWhatsAppRequest(
        call_id="call-1",
        phone="8688664337",
        business_type="fashion",
        product_count="200",
        required_features=["payments", "inventory", "WhatsApp integration"],
        budget_range="₹80,000",
        timeline="two weeks",
        summary="Customer is classified HOT with score 95.",
    )

    message = build_high_intent_message(request)

    assert message.startswith("Hi,\n\nGreat speaking with you.")
    assert "fashion e-commerce website" in message
    assert "around 200 products" in message
    assert "payments, inventory and WhatsApp integration" in message
    assert "₹80,000" in message
    assert "two weeks" in message
    assert "HOT" not in message
    assert "score" not in message
    assert "Sai" not in message


def test_message_omits_missing_fields_without_fabricating_details() -> None:
    request = HighIntentWhatsAppRequest(call_id="call-2", phone="8688664337")

    message = build_high_intent_message(request)

    assert "budget" not in message.lower()
    assert "timeline" not in message.lower()
    assert "None" not in message
    assert "Sharing the details here" in message


def test_final_followup_carries_number_and_the_lead_s_own_words() -> None:
    from app.schemas.complete_call import CompleteCallRequest
    from app.services.message_builder import build_final_followup

    request = CompleteCallRequest(
        call_id="call-9",
        phone="8688664337",
        business_type="fashion",
        product_count="150",
        required_features=["payment gateway"],
        budget_range="80k-1L",
        timeline="six weeks",
        important_statements=[
            "Diwali se pehle live karna hai",
            "abhi Instagram pe hi bech rahe hain",
        ],
    )

    message = build_final_followup(request, "Nischal Saxena", "+919999999999")

    assert '"Diwali se pehle live karna hai"' in message
    assert '"abhi Instagram pe hi bech rahe hain"' in message
    assert message.endswith("Nischal Saxena\n+919999999999")


def test_final_followup_omits_quote_block_when_nothing_was_captured() -> None:
    from app.schemas.complete_call import CompleteCallRequest
    from app.services.message_builder import build_final_followup

    request = CompleteCallRequest(call_id="call-10", phone="8688664337")
    message = build_final_followup(request, "Nischal Saxena", "+919999999999")

    assert "You said" not in message
    assert message.endswith("Nischal Saxena\n+919999999999")
