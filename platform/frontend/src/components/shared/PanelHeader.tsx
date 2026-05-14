import React from 'react';

export function PanelHeader({ title, subtitle, icon, actions }: { title: string; subtitle: string; icon: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="ph">
      <div className="ph-left">
        <h2>{icon}{title}</h2>
        <div className="ph-sub">{subtitle}</div>
      </div>
      <div className="ph-right">{actions}</div>
    </div>
  );
}
