import React from 'react';

export function PanelHeader({ title, subtitle, icon, actions }: { title: string; subtitle: string; icon: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="ph">
      <div className="ph-left">
        <h1 className="ph-title">{icon}{title}</h1>
        <div className="ph-sub">{subtitle}</div>
      </div>
      <div className="ph-right">{actions}</div>
    </header>
  );
}
