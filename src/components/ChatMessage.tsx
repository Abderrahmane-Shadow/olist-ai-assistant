import React, { useState } from 'react';
import { User, Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, TrendingUp, TrendingDown, Minus, Database, ChevronDown, ChevronUp, BarChart3, PieChart as PieChartIcon, Star, MessageSquareQuote } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend as RechartsLegend,
} from 'recharts';
import { Message, MetricCard } from '@/types/chat';

const CHART_COLORS = ['#169b75', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ec4899', '#10b981', '#f97316', '#06b6d4'];

const formatChartValue = (val: number, unit?: string) => {
  if (unit === 'R$') {
    return `R$ ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (unit === '%') {
    return `${val}%`;
  }
  return val.toLocaleString();
};

const CustomChartTooltip = ({ active, payload, label, unit }: any) => {
  if (active && payload && payload.length) {
    const title = label || payload[0]?.name;
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-md p-2.5 text-xs z-50">
        <p className="font-semibold text-gray-800 mb-1">{title}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} className="text-gray-600 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color || entry.fill || '#169b75' }} />
            <span className="font-medium text-gray-700">{entry.name?.replace(/_/g, ' ')}:</span>
            <span className="font-semibold text-gray-900">{formatChartValue(Number(entry.value), unit)}</span>
          </p>
        ))}
      </div>
    );
  }
  return null;
};

interface ChatMessageProps {
  message: Message;
  onRegenerate?: () => void;
  isLastAssistant?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  onRegenerate,
  isLastAssistant = false,
}) => {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'liked' | 'disliked' | null>(null);
  const [showSql, setShowSql] = useState(false);
  const [showReviews, setShowReviews] = useState(true);
  const isUser = message.sender === 'user';

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text).catch(() => {
      // Fallback for environments where clipboard API is restricted
      const el = document.createElement('textarea');
      el.value = message.text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    });
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderFormattedText = (content: string) => {
    const lines = content.split('\n');
    let inCodeBlock = false;
    let codeBlockLines: string[] = [];

    const elements: React.ReactNode[] = [];

    lines.forEach((line, idx) => {
      const trimmed = line.trim();

      if (trimmed.startsWith('```')) {
        if (inCodeBlock) {
          // Flush code block
          elements.push(
            <div key={`code-${idx}`} className="my-2 p-3 bg-gray-900 rounded-lg text-gray-100 font-mono text-xs overflow-x-auto leading-relaxed border border-gray-800">
              <code>{codeBlockLines.join('\n')}</code>
            </div>
          );
          codeBlockLines = [];
          inCodeBlock = false;
        } else {
          inCodeBlock = true;
          codeBlockLines = [];
        }
        return;
      }

      if (inCodeBlock) {
        codeBlockLines.push(line);
        return;
      }

      if (!trimmed) {
        elements.push(<div key={`blank-${idx}`} className="h-1.5" />);
        return;
      }

      if (trimmed === '---' || trimmed === '***' || trimmed === '___') {
        elements.push(<hr key={`hr-${idx}`} className="my-3 border-gray-200" />);
        return;
      }

      if (trimmed.startsWith('##### ')) {
        elements.push(
          <h6 key={`h5-${idx}`} className="text-xs font-semibold uppercase tracking-wider text-gray-800 mt-2.5 mb-1">
            {renderInline(trimmed.slice(6))}
          </h6>
        );
        return;
      }

      if (trimmed.startsWith('#### ')) {
        elements.push(
          <h5 key={`h4-${idx}`} className="text-sm font-semibold text-gray-900 mt-3 mb-1">
            {renderInline(trimmed.slice(5))}
          </h5>
        );
        return;
      }

      if (trimmed.startsWith('### ')) {
        elements.push(
          <h4 key={`h3-${idx}`} className="text-sm font-bold text-gray-900 mt-3.5 mb-1.5">
            {renderInline(trimmed.slice(4))}
          </h4>
        );
        return;
      }

      if (trimmed.startsWith('## ')) {
        elements.push(
          <h3 key={`h2-${idx}`} className="text-base font-bold text-gray-900 mt-4 mb-2">
            {renderInline(trimmed.slice(3))}
          </h3>
        );
        return;
      }

      if (trimmed.startsWith('# ')) {
        elements.push(
          <h2 key={`h1-${idx}`} className="text-lg font-bold text-gray-900 mt-4 mb-2">
            {renderInline(trimmed.slice(2))}
          </h2>
        );
        return;
      }

      if (trimmed.startsWith('> ')) {
        elements.push(
          <blockquote
            key={`bq-${idx}`}
            className="border-l-2 border-[#169b75] pl-3 py-1.5 my-2 bg-[#f0faf7] rounded-r text-gray-700 text-sm leading-relaxed"
          >
            {renderInline(trimmed.slice(2))}
          </blockquote>
        );
        return;
      }

      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        elements.push(
          <div key={`li-${idx}`} className="flex items-start gap-2 ml-1 my-0.5">
            <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-[#169b75] shrink-0" />
            <span className="text-sm text-gray-700 leading-relaxed">{renderInline(trimmed.slice(2))}</span>
          </div>
        );
        return;
      }

      const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
      if (numMatch) {
        elements.push(
          <div key={`oli-${idx}`} className="flex items-start gap-2 ml-1 my-0.5">
            <span className="text-xs text-gray-500 font-semibold mt-0.5 shrink-0 w-4">
              {numMatch[1]}.
            </span>
            <span className="text-sm text-gray-700 leading-relaxed">{renderInline(numMatch[2])}</span>
          </div>
        );
        return;
      }

      elements.push(
        <p key={`p-${idx}`} className="text-sm text-gray-700 leading-relaxed">
          {renderInline(trimmed)}
        </p>
      );
    });

    if (inCodeBlock && codeBlockLines.length > 0) {
      elements.push(
        <div key="code-unclosed" className="my-2 p-3 bg-gray-900 rounded-lg text-gray-100 font-mono text-xs overflow-x-auto leading-relaxed border border-gray-800">
          <code>{codeBlockLines.join('\n')}</code>
        </div>
      );
    }

    return <div className="space-y-1.5">{elements}</div>;
  };

  /**
   * Renders inline code (`code`), bold (**text**) and italic (*text*, _text_) markup.
   */
  const renderInline = (text: string): React.ReactNode[] => {
    const tokens: React.ReactNode[] = [];
    const regex = /(`[^`]+?`|\*\*[^*]+?\*\*|\*[^*]+?\*|_[^_]+?_)/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        tokens.push(text.slice(lastIndex, match.index));
      }

      const raw = match[0];
      if (raw.startsWith('`')) {
        tokens.push(
          <code
            key={match.index}
            className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-800 font-mono text-xs border border-gray-200"
          >
            {raw.slice(1, -1)}
          </code>
        );
      } else if (raw.startsWith('**')) {
        tokens.push(
          <strong key={match.index} className="font-semibold text-gray-900">
            {raw.slice(2, -2)}
          </strong>
        );
      } else if (raw.startsWith('_')) {
        tokens.push(
          <em key={match.index} className="italic text-gray-700">
            {raw.slice(1, -1)}
          </em>
        );
      } else {
        tokens.push(
          <em key={match.index} className="italic text-gray-700">
            {raw.slice(1, -1)}
          </em>
        );
      }
      lastIndex = match.index + raw.length;
    }

    if (lastIndex < text.length) {
      tokens.push(text.slice(lastIndex));
    }

    return tokens;
  };

  const trendIcon = (trend?: MetricCard['trend']) => {
    if (!trend) return null;
    if (trend.direction === 'up')
      return <TrendingUp className="w-3 h-3 text-[#169b75] inline mr-0.5" />;
    if (trend.direction === 'down')
      return <TrendingDown className="w-3 h-3 text-red-500 inline mr-0.5" />;
    return <Minus className="w-3 h-3 text-gray-400 inline mr-0.5" />;
  };

  return (
    <div
      className={`w-full px-4 sm:px-6 py-5 ${
        isUser ? 'bg-white' : 'bg-gray-50 border-y border-gray-100'
      }`}
    >
      <div className="max-w-3xl mx-auto flex gap-3">
        {/* Avatar */}
        <div className="shrink-0 mt-0.5">
          {isUser ? (
            <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center">
              <User className="w-3.5 h-3.5 text-gray-600" />
            </div>
          ) : (
            <div className="w-7 h-7 rounded-md bg-[#169b75] flex items-center justify-center">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Name row */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-gray-800">
              {isUser ? 'You' : 'Olist AI'}
            </span>
            <span className="text-[11px] text-gray-400">{message.timestamp}</span>
          </div>

          {/* User message bubble */}
          {isUser ? (
            <div className="inline-block bg-white border border-gray-200 rounded-lg px-3.5 py-2.5 text-sm text-gray-800 shadow-sm">
              <p className="whitespace-pre-wrap">{message.text}</p>
            </div>
          ) : (
            /* AI response */
            <div className="space-y-4">
              {/* Formatted text */}
              <div>{renderFormattedText(message.text)}</div>

              {/* Metric cards */}
              {message.metrics && message.metrics.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  {message.metrics.map((m, i) => (
                    <div
                      key={i}
                      className="p-3 rounded-lg border border-gray-200 bg-white shadow-sm"
                    >
                      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400 mb-1">
                        {m.label}
                      </p>
                      <p className="text-lg font-semibold text-gray-900">{m.value}</p>
                      {(m.subtext || m.trend) && (
                        <div className="mt-1 flex items-center justify-between text-xs text-gray-400 gap-2">
                          {m.subtext && <span className="truncate">{m.subtext}</span>}
                          {m.trend && (
                            <span className="flex items-center shrink-0">
                              {trendIcon(m.trend)}
                              {m.trend.value}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Automatic Interactive Visual Chart */}
              {message.chart && message.chart.data && message.chart.data.length > 0 && (
                <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                  <div className="flex items-center justify-between mb-3 border-b border-gray-100 pb-2.5">
                    <div className="flex items-center gap-2">
                      {message.chart.type === 'line' ? (
                        <TrendingUp className="w-4 h-4 text-[#169b75]" />
                      ) : message.chart.type === 'pie' ? (
                        <PieChartIcon className="w-4 h-4 text-[#169b75]" />
                      ) : (
                        <BarChart3 className="w-4 h-4 text-[#169b75]" />
                      )}
                      <h5 className="text-xs font-semibold text-gray-800 tracking-wide">
                        {message.chart.title}
                      </h5>
                    </div>
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-[#169b75] border border-emerald-100 uppercase tracking-wider">
                      {message.chart.type} chart
                    </span>
                  </div>

                  <div className="w-full h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      {message.chart.type === 'line' ? (
                        <LineChart data={message.chart.data} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                          <XAxis
                            dataKey={message.chart.x_key}
                            tick={{ fontSize: 10, fill: '#6b7280' }}
                            tickLine={false}
                            axisLine={{ stroke: '#e5e7eb' }}
                          />
                          <YAxis
                            tick={{ fontSize: 10, fill: '#6b7280' }}
                            tickLine={false}
                            axisLine={{ stroke: '#e5e7eb' }}
                            tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)}
                          />
                          <RechartsTooltip content={<CustomChartTooltip unit={message.chart.unit} />} />
                          {message.chart.y_keys.map((yKey, idx) => (
                            <Line
                              key={yKey}
                              type="monotone"
                              dataKey={yKey}
                              stroke={CHART_COLORS[idx % CHART_COLORS.length]}
                              strokeWidth={2.5}
                              dot={{ r: 3, fill: CHART_COLORS[idx % CHART_COLORS.length] }}
                              activeDot={{ r: 5 }}
                            />
                          ))}
                        </LineChart>
                      ) : message.chart.type === 'pie' ? (
                        <PieChart margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                          <Pie
                            data={message.chart.data}
                            dataKey={message.chart.y_keys[0]}
                            nameKey={message.chart.x_key}
                            cx="50%"
                            cy="50%"
                            innerRadius={45}
                            outerRadius={75}
                            paddingAngle={3}
                          >
                            {message.chart.data.map((_, index) => (
                              <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                            ))}
                          </Pie>
                          <RechartsTooltip content={<CustomChartTooltip unit={message.chart.unit} />} />
                          <RechartsLegend
                            wrapperStyle={{ fontSize: 11, paddingTop: 10 }}
                            formatter={(val) => <span className="text-gray-700 text-xs">{val}</span>}
                          />
                        </PieChart>
                      ) : (
                        <BarChart data={message.chart.data} margin={{ top: 10, right: 10, left: -10, bottom: 25 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" vertical={false} />
                          <XAxis
                            dataKey={message.chart.x_key}
                            tick={{ fontSize: 10, fill: '#6b7280' }}
                            angle={-25}
                            textAnchor="end"
                            interval={0}
                            tickLine={false}
                            axisLine={{ stroke: '#e5e7eb' }}
                          />
                          <YAxis
                            tick={{ fontSize: 10, fill: '#6b7280' }}
                            tickLine={false}
                            axisLine={{ stroke: '#e5e7eb' }}
                            tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v)}
                          />
                          <RechartsTooltip content={<CustomChartTooltip unit={message.chart.unit} />} />
                          {message.chart.y_keys.map((yKey, idx) => (
                            <Bar
                              key={yKey}
                              dataKey={yKey}
                              fill={CHART_COLORS[idx % CHART_COLORS.length]}
                              radius={[4, 4, 0, 0]}
                            />
                          ))}
                        </BarChart>
                      )}
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Breakdown bars */}
              {message.breakdown && (
                <div className="p-4 rounded-lg border border-gray-200 bg-white">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
                    {message.breakdown.title}
                  </p>
                  <div className="space-y-2.5">
                    {message.breakdown.items.map((item, i) => (
                      <div key={i}>
                        <div className="flex justify-between text-xs text-gray-700 mb-1">
                          <span>{item.label}</span>
                          <span className="font-medium text-gray-900">{item.value}</span>
                        </div>
                        {item.percentage !== undefined && (
                          <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-[#169b75] h-1.5 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(item.percentage, 100)}%` }}
                            />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Customer Review Evidence & Citations */}
              {message.review_citations && message.review_citations.length > 0 && (
                <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
                  <button
                    onClick={() => setShowReviews(!showReviews)}
                    className="w-full flex items-center justify-between px-3.5 py-2.5 bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquareQuote className="w-4 h-4 text-[#169b75]" />
                      <span className="uppercase tracking-wider">
                        Customer Review Evidence ({message.review_citations.length} cited)
                      </span>
                    </div>
                    <div className="flex items-center gap-1 text-[11px] text-gray-400">
                      <span>{showReviews ? 'Hide Reviews' : 'Show Reviews'}</span>
                      {showReviews ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </div>
                  </button>
                  {showReviews && (
                    <div className="p-3 space-y-2.5 divide-y divide-gray-100">
                      {message.review_citations.map((rev, rIdx) => {
                        const isPos = rev.score >= 4;
                        const isNeg = rev.score <= 2;
                        const badgeColor = isPos
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : isNeg
                          ? 'bg-rose-50 text-rose-700 border-rose-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200';

                        return (
                          <div key={rev.review_id || rIdx} className={rIdx > 0 ? 'pt-2.5' : ''}>
                            <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold text-gray-900">
                                  #{rIdx + 1}
                                </span>
                                <div className="flex items-center text-amber-400 text-xs" title={`${rev.score} / 5 stars`}>
                                  {[1, 2, 3, 4, 5].map((star) => (
                                    <Star
                                      key={star}
                                      className={`w-3.5 h-3.5 ${
                                        star <= rev.score ? 'fill-amber-400 text-amber-400' : 'text-gray-300'
                                      }`}
                                    />
                                  ))}
                                  <span className="ml-1 text-[11px] font-medium text-gray-600">
                                    {rev.score}.0
                                  </span>
                                </div>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium uppercase tracking-wider ${badgeColor}`}>
                                  {rev.sentiment || (isPos ? 'positive' : isNeg ? 'negative' : 'neutral')}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 text-[11px] text-gray-400">
                                {rev.category && (
                                  <span className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                                    {rev.category.replace(/_/g, ' ')}
                                  </span>
                                )}
                                {rev.customer_state && (
                                  <span className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                                    {rev.customer_state}
                                  </span>
                                )}
                                {rev.creation_date && (
                                  <span>{rev.creation_date}</span>
                                )}
                              </div>
                            </div>
                            {rev.title && (
                              <p className="text-xs font-semibold text-gray-800 mb-1">
                                {rev.title}
                              </p>
                            )}
                            <p className="text-xs text-gray-700 bg-gray-50/70 border-l-2 border-[#169b75] pl-2.5 py-1.5 rounded-r italic leading-relaxed">
                              "{rev.comment}"
                            </p>
                            <p className="text-[10px] font-mono text-gray-400 mt-1">
                              Review ID: {rev.review_id}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Dynamic Query Result Table (Multi-row results) */}
              {message.columns && message.rows && message.rows.length > 0 && (
                <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
                  <div className="px-3.5 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-gray-600">
                      Query Results ({message.rows.length} {message.rows.length === 1 ? 'row' : 'rows'})
                    </span>
                  </div>
                  <div className="overflow-x-auto max-h-72">
                    <table className="w-full text-left text-xs text-gray-700">
                      <thead className="bg-gray-50 text-[11px] text-gray-500 uppercase tracking-wider border-b border-gray-200 sticky top-0">
                        <tr>
                          {message.columns.map((col, idx) => (
                            <th key={idx} className="px-3 py-2 font-medium whitespace-nowrap">
                              {col.replace(/_/g, ' ')}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 font-mono text-[11px]">
                        {message.rows.map((row, rIdx) => (
                          <tr key={rIdx} className="hover:bg-gray-50 transition-colors">
                            {message.columns!.map((col, cIdx) => {
                              const val = row[col];
                              const displayVal = typeof val === 'number'
                                ? (val % 1 !== 0 ? val.toFixed(2) : val.toLocaleString())
                                : (val !== null && val !== undefined ? String(val) : '-');
                              return (
                                <td key={cIdx} className="px-3 py-1.5 whitespace-nowrap text-gray-800">
                                  {displayVal}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Collapsible Executed SQL Query */}
              {message.sql_query && (
                <div className="rounded-lg border border-gray-200 bg-white overflow-hidden text-xs">
                  <button
                    onClick={() => setShowSql(!showSql)}
                    className="w-full flex items-center justify-between px-3 py-2 text-gray-600 hover:bg-gray-50 transition-colors font-medium text-left"
                  >
                    <div className="flex items-center gap-1.5 text-gray-700">
                      <Database className="w-3.5 h-3.5 text-[#169b75]" />
                      <span>PostgreSQL Query Executed</span>
                    </div>
                    <div className="flex items-center gap-1 text-[11px] text-gray-400">
                      <span>{showSql ? 'Hide SQL' : 'View SQL'}</span>
                      {showSql ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </div>
                  </button>
                  {showSql && (
                    <div className="border-t border-gray-200 bg-gray-900 p-3 text-gray-100 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                      <code>{message.sql_query}</code>
                    </div>
                  )}
                </div>
              )}

              {/* Action toolbar */}
              <div className="flex items-center gap-0.5 pt-1">
                {/* Copy */}
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1.5 px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                  title="Copy response"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-[#169b75]" />
                      <span className="text-[#169b75]">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy</span>
                    </>
                  )}
                </button>

                <div className="w-px h-3 bg-gray-200 mx-1" />

                {/* Thumbs up */}
                <button
                  onClick={() => setFeedback(feedback === 'liked' ? null : 'liked')}
                  className={`p-1 rounded transition-colors ${
                    feedback === 'liked'
                      ? 'text-[#169b75] bg-[#e8f7f3]'
                      : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100'
                  }`}
                  title="Helpful"
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>

                {/* Thumbs down */}
                <button
                  onClick={() => setFeedback(feedback === 'disliked' ? null : 'disliked')}
                  className={`p-1 rounded transition-colors ${
                    feedback === 'disliked'
                      ? 'text-red-500 bg-red-50'
                      : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100'
                  }`}
                  title="Not helpful"
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>

                {/* Regenerate — only on last AI message */}
                {isLastAssistant && onRegenerate && (
                  <>
                    <div className="w-px h-3 bg-gray-200 mx-1" />
                    <button
                      onClick={onRegenerate}
                      className="flex items-center gap-1.5 px-2 py-1 rounded text-xs text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                      title="Regenerate response"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Regenerate</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
