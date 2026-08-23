from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.schemas.complete_call import CompleteCallRequest


def build_high_intent_message(
    request: HighIntentWhatsAppRequest,
    developer_name: str = "",
    developer_phone: str = "",
) -> str:
    paragraphs = ["Hi,", "Great speaking with you."]

    description_parts: list[str] = []
    if request.business_type:
        description_parts.append(f"a {request.business_type} e-commerce website")
    else:
        description_parts.append("an e-commerce website")
    if request.product_count:
        description_parts.append(f"for around {request.product_count} products")
    if request.required_features:
        description_parts.append(f"with {_human_join(request.required_features)}")
    if len(description_parts) > 1 or request.business_type:
        paragraphs.append(
            "From our conversation, you're looking to build "
            + " ".join(description_parts)
            + "."
        )

    details: list[str] = []
    if request.budget_range:
        details.append(f"a budget of around {request.budget_range}")
    if request.timeline:
        details.append(f"a target launch within {request.timeline}")
    if details:
        paragraphs.append("You mentioned " + " and ".join(details) + ".")

    paragraphs.append(
        "Sharing the details here so they're easy to refer back to while we continue "
        "the conversation."
    )
    paragraphs.extend(_signature(developer_name, developer_phone))
    return "\n\n".join(paragraphs)


def _quoted_statements(statements: list[str]) -> str:
    """Echo the lead's own words back so the follow-up cannot read as a template."""
    cleaned = [statement.strip() for statement in statements if statement.strip()]
    if not cleaned:
        return ""
    quoted = [f'"{statement}"' for statement in cleaned[:3]]
    return (
        "You said " + _human_join(quoted) + " - that is exactly what I will design around."
    )


def _signature(developer_name: str, developer_phone: str) -> list[str]:
    """Close with the name and a reachable number, per the follow-up brief."""
    lines = [line for line in (developer_name.strip(), developer_phone.strip()) if line]
    return ["\n".join(lines)] if lines else []


def _human_join(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    if len(cleaned) <= 1:
        return "".join(cleaned)
    if len(cleaned) == 2:
        return " and ".join(cleaned)
    return ", ".join(cleaned[:-1]) + f" and {cleaned[-1]}"


def build_final_followup(
    request: CompleteCallRequest,
    developer_name: str,
    developer_phone: str = "",
) -> str:
    paragraphs = ["Hi,", "Great speaking with you."]
    details: list[str] = []
    if request.business_type:
        details.append(f"a {request.business_type} e-commerce website")
    else:
        details.append("an e-commerce website")
    if request.product_count:
        details.append(f"for around {request.product_count} products")
    if request.required_features:
        details.append(f"with {_human_join(request.required_features)}")
    if any((request.business_type, request.product_count, request.required_features)):
        paragraphs.append("From our conversation, you're looking to build " + " ".join(details) + ".")
    commercial: list[str] = []
    if request.budget_range:
        commercial.append(f"a budget of around {request.budget_range}")
    if request.timeline:
        commercial.append(f"a target launch within {request.timeline}")
    if commercial:
        paragraphs.append("You mentioned " + " and ".join(commercial) + ".")
    quoted = _quoted_statements(request.important_statements)
    if quoted:
        paragraphs.append(quoted)
    paragraphs.append(
        "I've also shared my resume and the architecture overview of the system that called you."
    )
    paragraphs.extend(_signature(developer_name, developer_phone))
    return "\n\n".join(paragraphs)
