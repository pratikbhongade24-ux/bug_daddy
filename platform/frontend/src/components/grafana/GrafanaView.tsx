'use client';

const GRAFANA_URL = 'http://13.205.34.252:3001';

export function GrafanaView() {
  return (
    <div className="grafana-view">
      <div className="grafana-header">
        <div className="grafana-header-left">
          <span className="grafana-title">Grafana</span>
          <span className="grafana-badge">Live</span>
        </div>
        <a
          href={GRAFANA_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="grafana-open-btn"
        >
          Open in new tab ↗
        </a>
      </div>
      <iframe
        src={GRAFANA_URL}
        className="grafana-frame"
        title="Grafana Dashboards"
        allow="fullscreen"
      />
    </div>
  );
}
