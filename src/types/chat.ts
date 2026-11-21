export interface MetricCard {
  label: string;
  value: string;
  subtext?: string;
  trend?: {
    direction: 'up' | 'down' | 'neutral';
    value: string;
  };
}

export interface ChartDataPoint {
  label: string;
  value: number;
  formattedValue?: string;
}

export interface ChartConfig {
  type: 'bar' | 'line' | 'pie';
  title: string;
  x_key: string;
  y_keys: string[];
  data: Record<string, any>[];
  x_label?: string;
  y_label?: string;
  unit?: string;
}

export interface ReviewCitation {
  review_id: string;
  order_id?: string;
  score: number;
  title?: string;
  comment: string;
  category?: string;
  customer_state?: string;
  creation_date?: string;
  sentiment?: 'positive' | 'neutral' | 'negative';
}

export interface SentimentSummary {
  total_reviews_analyzed: number;
  average_score: number;
  positive_count: number;
  positive_percentage: number;
  neutral_count: number;
  neutral_percentage: number;
  negative_count: number;
  negative_percentage: number;
  sentiment_label: 'predominantly_positive' | 'mixed' | 'predominantly_negative';
  top_aspects?: Record<string, any>[];
}

export interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  metrics?: MetricCard[];
  breakdown?: {
    title: string;
    items: { label: string; value: string; percentage?: number }[];
  };
  chart?: ChartConfig;
  review_citations?: ReviewCitation[];
  sentiment_summary?: SentimentSummary;
  sql_query?: string;
  columns?: string[];
  rows?: Record<string, any>[];
  metadata?: Record<string, any>;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
}

export interface SuggestedQuestion {
  id: string;
  title: string;
  description: string;
  category: 'Revenue' | 'Products' | 'Satisfaction' | 'Logistics';
  icon: 'DollarSign' | 'TrendingUp' | 'AlertCircle' | 'Clock';
}
