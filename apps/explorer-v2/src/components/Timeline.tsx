import React from 'react';

type TimelineEvent = {
  time: string;
  from: string;
  to: string;
  amount: number;
  asset: string;
  tx: string;
};

type TimelineProps = {
  events: TimelineEvent[];
  onFocusNode?: (addr: string) => void;
};

export function Timeline({ events, onFocusNode }: TimelineProps) {
  if (!events || events.length === 0) {
    return (
      <div className="timeline">
        <div className="section-label">Timeline / Attribution</div>
        <p className="empty">No timeline events yet. Load data or expand graph to populate attribution history.</p>
      </div>
    );
  }

  return (
    <div className="timeline">
      <div className="section-label">Timeline / Attribution ({events.length} events)</div>
      <div className="timeline-list">
        {events.slice(0, 50).map((ev, idx) => (
          <div key={idx} className="timeline-event">
            <span className="time">{ev.time ? new Date(ev.time).toLocaleString() : 'unknown'}</span>
            <span className="flow">
              <a href="#" onClick={(e) => { e.preventDefault(); onFocusNode?.(ev.from); }}>
                {ev.from.slice(0, 8)}...
              </a>
              {' → '}
              <a href="#" onClick={(e) => { e.preventDefault(); onFocusNode?.(ev.to); }}>
                {ev.to.slice(0, 8)}...
              </a>
            </span>
            <span className="amount">
              {ev.amount.toFixed(4)} {ev.asset}
            </span>
            <span className="tx" title={ev.tx}>
              {ev.tx ? ev.tx.slice(0, 10) + '...' : ''}
            </span>
          </div>
        ))}
      </div>
      {events.length > 50 && <p className="truncated">... showing first 50 (full list via getTimeline() or export)</p>}
      <p className="help">Click addresses to focus nodes. Use "Export Evidence Bundle" for full deterministic audit trail of this timeline.</p>
    </div>
  );
}
