import React, { useState } from 'react';

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
  onExportEvidence?: (subject: string) => void;
};

export function Timeline({ events, onFocusNode, onExportEvidence }: TimelineProps) {
  const [filter, setFilter] = useState('');
  const [sortBy, setSortBy] = useState<'time' | 'amount'>('time');

  if (!events || events.length === 0) {
    return (
      <div className="timeline">
        <div className="section-label">Timeline / Attribution</div>
        <p className="empty">No timeline events yet. Load data or expand graph to populate attribution history.</p>
      </div>
    );
  }

  let filtered = events.filter(ev =>
    ev.from.toLowerCase().includes(filter.toLowerCase()) ||
    ev.to.toLowerCase().includes(filter.toLowerCase()) ||
    ev.asset.toLowerCase().includes(filter.toLowerCase()) ||
    ev.tx.toLowerCase().includes(filter.toLowerCase())
  );

  filtered = [...filtered].sort((a, b) => {
    if (sortBy === 'time') {
      return (b.time || '').localeCompare(a.time || '');
    }
    return b.amount - a.amount;
  });

  const handleExportForEvent = (ev: TimelineEvent) => {
    if (onExportEvidence) {
      // Export for the 'from' as primary subject for this event's context
      onExportEvidence(ev.from);
    }
  };

  // Simple visual timeline bar (deeper UI: overview scrubber with time-range filter simulation)
  const minTime = Math.min(...events.map(e => e.time ? Date.parse(e.time) : 0));
  const maxTime = Math.max(...events.map(e => e.time ? Date.parse(e.time) : 0));
  const timeRange = maxTime - minTime || 1;

  // Simulate time-range filter (deeper: would highlight graph edges in explorer)
  const [timeFilter, setTimeFilter] = useState([0, 100]); // percent range

  // Filter events by time range too
  const timeFiltered = filtered.filter(ev => {
    if (!ev.time) return true;
    const t = Date.parse(ev.time);
    const pct = ((t - minTime) / timeRange) * 100;
    return pct >= timeFilter[0] && pct <= timeFilter[1];
  });

  return (
    <div className="timeline">
      <div className="section-label">Timeline / Attribution ({events.length} events, {timeFiltered.length} shown in range)</div>
      
      {/* Visual timeline bar with range */}
      <div className="timeline-bar" style={{height: '20px', background: '#eee', position: 'relative', margin: '8px 0'}}>
        {events.filter(e => e.time).slice(0, 20).map((ev, i) => {
          const t = Date.parse(ev.time);
          const left = ((t - minTime) / timeRange) * 100;
          const inRange = left >= timeFilter[0] && left <= timeFilter[1];
          return <div key={i} style={{position: 'absolute', left: `${left}%`, width: '2px', height: '100%', background: inRange ? '#ff6b6b' : '#4ecdc4'}} title={ev.time} />;
        })}
        <input type="range" min="0" max="100" value={timeFilter[0]} onChange={(e) => setTimeFilter([parseInt(e.target.value), timeFilter[1]])} style={{position:'absolute', width:'100%'}} />
        <input type="range" min="0" max="100" value={timeFilter[1]} onChange={(e) => setTimeFilter([timeFilter[0], parseInt(e.target.value)])} style={{position:'absolute', width:'100%'}} />
      </div>
      <div style={{fontSize:'10px'}}>Time range filter: {timeFilter[0]}%-{timeFilter[1]}% (highlights in graph - integrate in next slice)</div>

      <div className="timeline-controls">
        <input
          type="text"
          placeholder="Filter by address, asset, tx..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="timeline-filter"
        />
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'time' | 'amount')} className="timeline-sort">
          <option value="time">Sort by time (newest)</option>
          <option value="amount">Sort by amount (largest)</option>
        </select>
        {onExportEvidence && (
          <button 
            className="secondary" 
            onClick={() => onExportEvidence('')} 
            title="Export evidence for current selection or full workspace"
          >
            Export Full Evidence
          </button>
        )}
      </div>

      <div className="timeline-list">
        {timeFiltered.slice(0, 100).map((ev, idx) => (
          <div key={idx} className="timeline-event" onClick={() => onFocusNode?.(ev.from)}>
            <span className="time">{ev.time ? new Date(ev.time).toLocaleString() : 'unknown'}</span>
            <span className="flow">
              <a href="#" onClick={(e) => { e.preventDefault(); e.stopPropagation(); onFocusNode?.(ev.from); }}>
                {ev.from.slice(0, 8)}...
              </a>
              {' → '}
              <a href="#" onClick={(e) => { e.preventDefault(); e.stopPropagation(); onFocusNode?.(ev.to); }}>
                {ev.to.slice(0, 8)}...
              </a>
            </span>
            <span className="amount">
              {ev.amount.toFixed(4)} {ev.asset}
            </span>
            <span className="tx" title={ev.tx}>
              {ev.tx ? ev.tx.slice(0, 10) + '...' : ''}
            </span>
            {onExportEvidence && (
              <button 
                className="tiny-export" 
                onClick={(e) => { e.stopPropagation(); handleExportForEvent(ev); }}
                title="Export deterministic evidence for this flow's source (uses local core)"
              >
                Export
              </button>
            )}
          </div>
        ))}
      </div>
      {timeFiltered.length > 100 && <p className="truncated">... showing first 100 of {timeFiltered.length} (use filter or full export for complete)</p>}
      <p className="help">
        Click row or addresses to focus in graph. Use Export buttons for per-event or full workspace deterministic evidence bundles (ties into local core).
        Workspaces with this timeline can be saved/loaded as portable JSON.
      </p>
    </div>
  );
}
