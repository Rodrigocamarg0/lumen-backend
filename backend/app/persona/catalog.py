from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaDefinition:
    id: str
    name: str
    subtitle: str
    description: str


PERSONA_CATALOG: tuple[PersonaDefinition, ...] = (
    PersonaDefinition(
        id="kardec",
        name="Allan Kardec",
        subtitle="Codificador do Espiritismo",
        description=(
            "O codificador da Doutrina Espírita responde com rigor científico e filosófico, "
            "citando as cinco obras fundamentais."
        ),
    ),
    PersonaDefinition(
        id="andreluiz",
        name="André Luiz",
        subtitle="Autor de Nosso Lar",
        description=(
            "Espírito que revelou os detalhes da vida no mundo espiritual através das obras "
            "psicografadas por Chico Xavier."
        ),
    ),
    PersonaDefinition(
        id="emmanuel",
        name="Emmanuel",
        subtitle="Mentor de Chico Xavier",
        description=(
            "Espírito de elevada hierarquia que orientou Chico Xavier por décadas, com sabedoria "
            "e fraternidade."
        ),
    ),
    PersonaDefinition(
        id="joanna",
        name="Joanna de Ângelis",
        subtitle="Psicologia e espiritualidade",
        description=(
            "Psicóloga espiritual que une ciência e fé nas obras psicografadas por Divaldo Franco."
        ),
    ),
)

PERSONA_IDS = {persona.id for persona in PERSONA_CATALOG}


def parse_enabled_personas(value: str) -> set[str]:
    requested = {item.strip() for item in value.split(",") if item.strip()}
    if not requested:
        return {"kardec"}
    if "all" in requested:
        return set(PERSONA_IDS)
    return requested & PERSONA_IDS


def enabled_personas(value: str) -> list[PersonaDefinition]:
    enabled_ids = parse_enabled_personas(value)
    return [persona for persona in PERSONA_CATALOG if persona.id in enabled_ids]
