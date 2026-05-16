'use client';

const GRAFANA_URL = '/grafana/';

export function GrafanaView() {
  return (
    <div className="grafana-view">
      <div className="grafana-header">
        <div className="grafana-header-left">
          <span className="grafana-title">Grafana</span>
          <span className="grafana-badge">Live</span>
        </div>
        <a
          href="https://bugdaddy.in/grafana/"
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
