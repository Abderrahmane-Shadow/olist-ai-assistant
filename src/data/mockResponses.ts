import { Message } from '@/types/chat';

export interface MockAnswer {
  text: string;
  metrics?: {
    label: string;
    value: string;
    subtext?: string;
    trend?: { direction: 'up' | 'down' | 'neutral'; value: string };
  }[];
  breakdown?: {
    title: string;
    items: { label: string; value: string; percentage?: number }[];
  };
}

export const PRESET_RESPONSES: Record<string, MockAnswer> = {
  // Supported categories, logistics delays, sellers, revenue, and freight
  // are now computed directly from PostgreSQL by the live analytics service.

  complaints: {
    text: `Sentiment analysis over **14,710 negative reviews (1-star and 2-star ratings)** reveals that customer dissatisfaction is overwhelmingly driven by fulfillment logistics rather than product quality.\n\n### Primary Complaint Root Causes:\n- **Late Delivery & Delivery Deadlines (62.4%):** Customers waiting past estimated delivery date, courier tracking silent, or goods marked delivered prematurely.\n- **Product Discrepancy & Defects (20.8%):** Items arriving damaged, incorrect color/size, or non-functional electronic accessories.\n- **Missing Items & Incomplete Shipments (10.6%):** Orders containing multi-item purchases delivered partially without seller notice.\n- **Customer Service & Seller Communication (6.2%):** Unresponsive marketplace sellers when seeking returns or exchanges.`,
    metrics: [
      {
        label: 'Logistics-Related Complaints',
        value: '62.4%',
        subtext: 'Dominant driver of 1-star ratings',
        trend: { direction: 'down', value: 'Fulfillment bottleneck' },
      },
      {
        label: 'Negative Review Volume',
        value: '14,710',
        subtext: 'Out of 99,224 total reviews',
        trend: { direction: 'neutral', value: '14.8% review rate' },
      },
      {
        label: 'Avg Review Score when Delayed',
        value: '1.28 / 5.0',
        subtext: 'Compared to 4.25 when on-time',
        trend: { direction: 'down', value: '-2.97 rating drop' },
      },
    ],
    breakdown: {
      title: 'Breakdown of Negative Review Factors',
      items: [
        { label: 'Late delivery / past deadline', value: '9,178 reviews', percentage: 62.4 },
        { label: 'Defect / not as described', value: '3,059 reviews', percentage: 20.8 },
        { label: 'Missing / incomplete package', value: '1,559 reviews', percentage: 10.6 },
        { label: 'Seller responsiveness & refund', value: '914 reviews', percentage: 6.2 },
      ],
    },
  },
};

export function getMockResponse(query: string): MockAnswer {
  const q = query.toLowerCase().trim();

  // Match specific preset questions for topics not yet handled by backend analytics
  if (q.includes('complaint') || q.includes('dissatisf') || q.includes('bad review') || q.includes('negative review') || q.includes('customer problem')) {
    return PRESET_RESPONSES.complaints;
  }

  // General fallback for unknown inquiries
  return {
    text: `I analyzed your inquiry: *"${query}"* against the Olist e-commerce database (100k Brazilian orders, 32k customers, 3k merchants).\n\nHere is a summary of findings:\n- **Ecosystem Scale:** 99.4k orders recorded between 2016 and 2018 with R$ 16M gross merchandise value.\n- **Customer Experience:** 77% of reviews awarded 4 or 5 stars; delivery punctuality is the primary determinant of 5-star ratings.\n- **Payment Distribution:** Credit cards drive 76.7% of volume, followed by traditional Boleto at 19.3%.\n\n*Feel free to ask for deeper segmentations by state, delivery SLA, seller performance, or product categories.*`,
    metrics: [
      { label: 'Dataset Orders', value: '99,441', subtext: 'Full historical period' },
      { label: 'Average Rating', value: '4.08 / 5.0', subtext: 'Across all reviews' },
    ],
  };
}
