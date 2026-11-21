import React from 'react';
import { DollarSign, TrendingUp, AlertCircle, Clock } from 'lucide-react';
import { SuggestedQuestion } from '@/types/chat';

interface WelcomeScreenProps {
  onSelectQuestion: (question: string) => void;
}

const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    id: 'revenue',
    title: 'What is the total revenue?',
    description: 'GMV, average order value, and peak sales periods.',
    category: 'Revenue',
    icon: 'DollarSign',
  },
  {
    id: 'category',
    title: 'Which product category performs best?',
    description: 'Top categories by revenue and by order volume.',
    category: 'Products',
    icon: 'TrendingUp',
  },
  {
    id: 'complaints',
    title: 'What are the most common customer complaints?',
    description: 'Review drivers, delivery issues, and defect rates.',
    category: 'Satisfaction',
    icon: 'AlertCircle',
  },
  {
    id: 'delayed',
    title: 'How many orders were delayed?',
    description: 'Delay rate, average days late, and regional breakdown.',
    category: 'Logistics',
    icon: 'Clock',
  },
];

const ICON_MAP = {
  DollarSign: DollarSign,
  TrendingUp: TrendingUp,
  AlertCircle: AlertCircle,
  Clock: Clock,
};

const CATEGORY_COLORS: Record<SuggestedQuestion['category'], string> = {
  Revenue: 'text-[#169b75]',
  Products: 'text-blue-600',
  Satisfaction: 'text-amber-600',
  Logistics: 'text-purple-600',
};

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({ onSelectQuestion }) => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 max-w-2xl mx-auto w-full animate-fade-in">
      {/* Logo mark */}
      <div className="w-10 h-10 rounded-lg bg-[#169b75] flex items-center justify-center mb-5">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
      </div>

      {/* Title */}
      <h1 className="text-2xl font-semibold text-gray-900 mb-1.5 tracking-tight">
        Olist AI Assistant
      </h1>
      <p className="text-sm text-gray-500 mb-8 text-center">
        Ask questions about Olist e-commerce data.
      </p>

      {/* Suggestion Cards */}
      <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {SUGGESTED_QUESTIONS.map((item) => {
          const Icon = ICON_MAP[item.icon];
          return (
            <button
              key={item.id}
              onClick={() => onSelectQuestion(item.title)}
              className="group text-left p-4 rounded-lg border border-gray-200 bg-white hover:border-[#169b75] hover:bg-[#f0faf7] transition-colors duration-150"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 shrink-0">
                  <Icon className={`w-4 h-4 ${CATEGORY_COLORS[item.category]}`} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 group-hover:text-gray-900 mb-0.5 leading-snug">
                    {item.title}
                  </p>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    {item.description}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
