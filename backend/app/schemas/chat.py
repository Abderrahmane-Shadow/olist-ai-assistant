from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class MessageHistoryItem(BaseModel):
    """Previous conversation turn for context."""
    role: str = Field(..., description="'user' or 'assistant'")
    text: str = Field(..., description="Message text content")
    sql_query: Optional[str] = Field(None, description="Executed SQL query in this turn if available")


class ChatRequest(BaseModel):
    """Incoming user chat query."""
    message: str = Field(..., min_length=1, description="User's natural language message or question")
    conversation_id: Optional[str] = Field(None, description="Client conversation identifier")
    history: Optional[List[MessageHistoryItem]] = Field(default_factory=list, description="Recent conversation turns (capped for security/performance)")


class MetricTrend(BaseModel):
    direction: str = Field(..., description="'up', 'down', or 'neutral'")
    value: str = Field(..., description="Trend delta or annotation")


class MetricCard(BaseModel):
    label: str
    value: str
    subtext: Optional[str] = None
    trend: Optional[MetricTrend] = None


class BreakdownItem(BaseModel):
    label: str
    value: str
    percentage: Optional[float] = None


class Breakdown(BaseModel):
    title: str
    items: List[BreakdownItem] = Field(default_factory=list)


class ChartConfig(BaseModel):
    """Structured chart configuration for frontend visualization."""
    type: str = Field(..., description="'bar', 'line', or 'pie'")
    title: str = Field(..., description="Descriptive chart title")
    x_key: str = Field(..., description="Column key for category/time dimension on X-axis or slice label")
    y_keys: List[str] = Field(..., description="Column keys for numeric series on Y-axis or slice values")
    data: List[Dict[str, Any]] = Field(..., description="Clean data rows formatted for recharts")
    x_label: Optional[str] = Field(None, description="Label for X-axis")
    y_label: Optional[str] = Field(None, description="Label for Y-axis")
    unit: Optional[str] = Field(None, description="Value unit (e.g. 'R$', '%', 'orders')")


class ReviewCitation(BaseModel):
    """Structured customer review evidence citation."""
    review_id: str
    order_id: Optional[str] = None
    score: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    comment: str
    category: Optional[str] = None
    customer_state: Optional[str] = None
    creation_date: Optional[str] = None
    sentiment: Optional[str] = Field(None, description="'positive', 'neutral', or 'negative'")


class SentimentSummary(BaseModel):
    """Quantitative sentiment breakdown for customer reviews."""
    total_reviews_analyzed: int
    average_score: float
    positive_count: int
    positive_percentage: float
    neutral_count: int
    neutral_percentage: float
    negative_count: int
    negative_percentage: float
    sentiment_label: str = Field(..., description="'predominantly_positive', 'mixed', or 'predominantly_negative'")
    top_aspects: Optional[List[Dict[str, Any]]] = None
    cohort_name: Optional[str] = None
    scope_description: Optional[str] = None
    platform_average_score: Optional[float] = 4.09
    platform_total_reviews: Optional[int] = 99224
    platform_text_reviews: Optional[int] = 42687


class ChatResponse(BaseModel):
    """Outgoing assistant response payload."""
    text: str = Field(..., description="Markdown-formatted natural language answer")
    source: str = Field(..., description="Source of response: 'postgresql', 'gemini', 'clarification', or 'unsupported'")
    intent: Optional[str] = Field(None, description="Identified analytical intent or query key")
    metrics: Optional[List[MetricCard]] = None
    breakdown: Optional[Breakdown] = None
    chart: Optional[ChartConfig] = Field(None, description="Automatic visual chart configuration if applicable")
    columns: Optional[List[str]] = Field(None, description="Dynamic tabular column headers")
    rows: Optional[List[Dict[str, Any]]] = Field(None, description="Dynamic tabular data rows")
    review_citations: Optional[List[ReviewCitation]] = Field(None, description="Actual customer review citations supporting the answer")
    sentiment_summary: Optional[SentimentSummary] = Field(None, description="Quantitative review sentiment analysis")
    sql_query: Optional[str] = None
    timestamp: Optional[str] = None
    language: Optional[str] = Field(default="en", description="Detected language ('en' or 'fr')")
    conversation_id: Optional[str] = Field(None, description="Persistent conversation identifier")
    daily_usage: Optional[Dict[str, Any]] = Field(None, description="Remaining daily question quota info")
    metadata: Optional[Dict[str, Any]] = None
