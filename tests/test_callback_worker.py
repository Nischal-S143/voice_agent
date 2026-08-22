from app.services.outbound_caller import OutboundCallRequest, UnconfiguredSarvamOutboundCaller


async def test_unconfigured_outbound_caller_never_claims_success() -> None:
    result = await UnconfiguredSarvamOutboundCaller().place_call(
        OutboundCallRequest(
            callback_id=19,
            phone="918688664337",
            context={"previous_summary": "Interested"},
        )
    )
    assert result.success is False
    assert result.error == "sarvam_outbound_not_configured"
    assert result.retryable is False
    assert result.call_id is None
