import { render, screen } from '@testing-library/react';
import StatusCard from '../../src/components/StatusCard';

describe('StatusCard', () => {
  it('renders loading state', () => {
    render(<StatusCard health={null} loading />);
    expect(screen.getByText('Loading status...')).toBeInTheDocument();
  });

  it('renders running status with paper trading badge', () => {
    render(
      <StatusCard
        health={{ running: true, paper_trading: true, last_error: null }}
        loading={false}
      />,
    );
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Paper Trading')).toBeInTheDocument();
  });

  it('renders error message when present', () => {
    render(
      <StatusCard
        health={{ running: false, paper_trading: false, last_error: 'Test error' }}
        loading={false}
      />,
    );
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByText(/Test error/)).toBeInTheDocument();
  });
});

