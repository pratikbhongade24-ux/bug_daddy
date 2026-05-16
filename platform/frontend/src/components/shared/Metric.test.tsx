import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Metric } from './Metric';

describe('Metric', () => {
  it('renders metric label and value', () => {
    render(<Metric label="Open Bugs" value={42} tone="hot" />);

    expect(screen.getByText('Open Bugs')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });
});
