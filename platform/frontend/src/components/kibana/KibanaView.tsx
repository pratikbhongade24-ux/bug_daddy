'use client';

const KIBANA_URL = '/kibana/';

export function KibanaView() {
  return (
    <div className="grafana-view">
      <div className="grafana-header">
        <div className="grafana-header-left">
          <span className="grafana-title">Kibana</span>
          <span className="grafana-badge">Live</span>
        </div>
        <a
          href="https://bugdaddy.in/kibana/"
          target="_blank"
          rel="noopener noreferrer"
          className="grafana-open-btn"
        >
          Open in new tab ↗
        </a>
      </div>
      <iframe
        src={KIBANA_URL}
        className="grafana-frame"
        title="Kibana Dashboards"
        allow="fullscreen"
      />
    </div>
  );
}
