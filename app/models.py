"""Pydantic schemas — the contracts between pipeline stages and the API."""

from pydantic import BaseModel, Field


class StartupProfile(BaseModel):
    """Output of the research agent (Phase A)."""
    company_name: str
    summary: str = Field(description="Short paragraph: the main product offering")
    products: list[str]
    technologies: list[str] = Field(description="Key technologies (AI, CV, IoT...)")
    target_industries: list[str]
    evidence_urls: list[str] = Field(description="Pages the claims are based on")


class DimensionScore(BaseModel):
    name: str = Field(description="e.g. technology_overlap, market_fit, "
                                  "integration_potential, competitive_complementarity, "
                                  "maturity_signals")
    score: int = Field(ge=1, le=10, description="1-10, higher is always better "
                       "(all dimensions share this polarity)")
    explanation: str


class MatchReport(BaseModel):
    """Output of the analyst agent (Phase B)."""
    comparison: str = Field(description="Offering vs Siemens DISW: overlap, "
                                        "complementarity, integration points")
    partnership_score: int = Field(ge=1, le=10)
    partnership_justification: str
    partner_similarity_score: int = Field(ge=1, le=10)
    partner_similarity_justification: str
    dimensions: list[DimensionScore] = Field(
        description="Exactly these five: technology_overlap, market_fit, "
                    "integration_potential, competitive_complementarity, "
                    "maturity_signals")


class AnalyzeRequest(BaseModel):
    url: str
    force: bool = False   # true = re-crawl + re-analyze even if cached
