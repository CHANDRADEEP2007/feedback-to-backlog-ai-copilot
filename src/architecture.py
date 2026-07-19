from __future__ import annotations

from dataclasses import dataclass
from html import escape


ARCHITECTURE_VIEWS = ("Current state", "Target state")


@dataclass(frozen=True)
class ArchitectureNode:
    name: str
    detail: str
    status: str


@dataclass(frozen=True)
class ArchitectureStage:
    title: str
    nodes: tuple[ArchitectureNode, ...]


CURRENT_ARCHITECTURE = (
    ArchitectureStage(
        "Feedback source",
        (
            ArchitectureNode(
                "Kaggle CSV",
                "Static multilingual support tickets",
                "built",
            ),
        ),
    ),
    ArchitectureStage(
        "Intelligence pipeline",
        (
            ArchitectureNode(
                "Structured extraction",
                "Gemini with deterministic fallback",
                "built",
            ),
            ArchitectureNode(
                "Layered deduplication",
                "RapidFuzz plus optional embeddings",
                "built",
            ),
            ArchitectureNode(
                "Explainable RICE",
                "Deterministic scoring and re-rank audit",
                "built",
            ),
        ),
    ),
    ArchitectureStage(
        "Memory and quality",
        (
            ArchitectureNode(
                "SQLite provenance",
                "Backlog, sources, score history, audit",
                "built",
            ),
            ArchitectureNode(
                "Evaluation harness",
                "Gold set, measured quality, guardrails",
                "built",
            ),
        ),
    ),
    ArchitectureStage(
        "Product outputs",
        (
            ArchitectureNode(
                "Streamlit workspace",
                "Dashboard, review, deltas, manual re-rank",
                "built",
            ),
            ArchitectureNode(
                "Jira Cloud sync",
                "Optional REST create, update, and bulk sync",
                "built",
            ),
        ),
    ),
)


TARGET_ARCHITECTURE = (
    ArchitectureStage(
        "Live feedback sources",
        (
            ArchitectureNode("Outlook and Teams", "Workplace feedback", "planned"),
            ArchitectureNode("Zoom and Slack", "Calls and collaboration", "planned"),
            ArchitectureNode("Intercom and Zendesk", "Support conversations", "planned"),
        ),
    ),
    ArchitectureStage(
        "Continuous intelligence",
        (
            ArchitectureNode("Ingestion service", "Event-driven collection", "planned"),
            ArchitectureNode("Structured extraction", "Reusable Gemini pipeline", "built"),
            ArchitectureNode("Hybrid deduplication", "Fuzzy and semantic matching", "built"),
            ArchitectureNode("Continuous re-scoring", "Priority refresh on new evidence", "planned"),
        ),
    ),
    ArchitectureStage(
        "Platform memory",
        (
            ArchitectureNode("Persistent cloud database", "Durable shared backlog", "planned"),
            ArchitectureNode("Evaluation harness", "Measured quality and guardrails", "built"),
            ArchitectureNode("Production telemetry", "Drift, latency, and cost monitoring", "planned"),
        ),
    ),
    ArchitectureStage(
        "Team workflows",
        (
            ArchitectureNode("Streamlit workspace", "Explainable review experience", "built"),
            ArchitectureNode("Jira orchestration", "Multiple projects and routing rules", "planned"),
            ArchitectureNode("Roles and permissions", "Shared reviewer governance", "planned"),
        ),
    ),
)


def architecture_stages(view: str) -> tuple[ArchitectureStage, ...]:
    if view == "Current state":
        return CURRENT_ARCHITECTURE
    if view == "Target state":
        return TARGET_ARCHITECTURE
    raise ValueError(f"Unknown architecture view: {view}")


def render_architecture(view: str) -> str:
    stages = architecture_stages(view)
    stage_markup = []
    for index, stage in enumerate(stages):
        nodes = "".join(
            f'<div class="arch-node arch-{escape(node.status)}">'
            '<div class="arch-node-heading">'
            f'<span class="arch-node-name">{escape(node.name)}</span>'
            f'<span class="arch-status">{escape(node.status.title())}</span>'
            '</div>'
            f'<div class="arch-node-detail">{escape(node.detail)}</div>'
            '</div>'
            for node in stage.nodes
        )
        stage_markup.append(
            f'<section class="arch-stage" aria-label="{escape(stage.title)}">'
            f'<div class="arch-stage-number">{index + 1:02d}</div>'
            f'<div class="arch-stage-title">{escape(stage.title)}</div>'
            f'<div class="arch-node-list">{nodes}</div>'
            '</section>'
        )
        if index < len(stages) - 1:
            stage_markup.append(
                '<div class="arch-arrow" aria-hidden="true"><span>→</span></div>'
            )

    description = (
        "Static feedback flows through the working MVP into a reviewed, traceable backlog."
        if view == "Current state"
        else "The MVP components become reusable services inside a continuous, multi-source product."
    )
    return (
        f'<div class="architecture-visual" role="img" aria-label="{escape(view)} architecture">'
        '<div class="arch-summary">'
        f'<span class="arch-view-label">{escape(view)}</span>'
        f'<span>{escape(description)}</span>'
        '</div>'
        f'<div class="arch-flow">{"".join(stage_markup)}</div>'
        '<div class="arch-legend" aria-label="Architecture status legend">'
        '<span><i class="arch-dot arch-dot-built"></i> Built today</span>'
        '<span><i class="arch-dot arch-dot-planned"></i> Planned evolution</span>'
        '</div></div>'
    )
