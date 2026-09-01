import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useWeeklyReview } from './useWeeklyReview';
import type { WeeklyReviewResponse } from '@/types/api';

const getWeeklyReview = vi.fn();

vi.mock('@/api/stats', () => ({
  statsApi: {
    getWeeklyReview: (offset: number) => getWeeklyReview(offset),
  },
}));

const RESPONSE: WeeklyReviewResponse = {
  week_start: '2026-08-24',
  week_end: '2026-08-30',
  total_minutes: 30,
  prev_total_minutes: 20,
  delta_minutes: 10,
  minutes_per_weekday: [10, 0, 20, 0, 0, 0, 0],
  daily_limit_enabled: false,
  daily_limit_minutes: 120,
  average_minutes_per_day: 4.3,
  most_played: null,
  never_played: [],
  never_played_total: 0,
};

const Probe = () => {
  const { data, weekOffset, goPrev, goNext } = useWeeklyReview(1);
  return (
    <div>
      <span data-testid="offset">{weekOffset}</span>
      <span data-testid="total">{data ? data.total_minutes : 'loading'}</span>
      <button onClick={goPrev}>prev</button>
      <button onClick={goNext}>next</button>
    </div>
  );
};

describe('useWeeklyReview', () => {
  beforeEach(() => {
    getWeeklyReview.mockReset();
    getWeeklyReview.mockResolvedValue(RESPONSE);
  });

  it('loads the requested week on mount', async () => {
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId('total')).toHaveTextContent('30'));
    expect(getWeeklyReview).toHaveBeenCalledWith(1);
  });

  it('steps back a week and re-fetches', async () => {
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId('total')).toHaveTextContent('30'));

    await act(async () => {
      screen.getByText('prev').click();
    });

    await waitFor(() => expect(screen.getByTestId('offset')).toHaveTextContent('2'));
    expect(getWeeklyReview).toHaveBeenLastCalledWith(2);
  });

  it('never steps past the current week', async () => {
    render(<Probe />);
    await waitFor(() => expect(screen.getByTestId('total')).toHaveTextContent('30'));

    await act(async () => {
      screen.getByText('next').click(); // 1 -> 0
      screen.getByText('next').click(); // clamped at 0
    });

    await waitFor(() => expect(screen.getByTestId('offset')).toHaveTextContent('0'));
  });
});
